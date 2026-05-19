"""知识图谱服务 — 实体抽取 / 关系抽取 / 图谱检索 / 统计"""

import json
import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.kg_models import KGEntity, KGRelation, EntityType
from app.core.embedding import embed_texts


def _llm_chat(messages: list, model: str = None, temperature: float = 0.1, max_tokens: int = 2000) -> str:
    """调用 LLM 完成对话（同步版本，供 asyncio 调用）"""
    from app.core.llm import get_llm_client
    client, default_model, _ = get_llm_client()
    resp = client.chat.completions.create(
        model=model or default_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""

logger = logging.getLogger(__name__)

# ─── Prompt 加载（从配置文件读取，支持热更新）──
def _get_prompt(prompt_type: str) -> dict:
    from app.core.llm import get_prompt
    return get_prompt(prompt_type)


def _parse_llm_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（兼容 markdown code block）"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        # 找到第一个 { 或 [ 开头的行
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                in_json = True
            if in_json:
                json_lines.append(line)
            if in_json and (stripped.endswith("}") or stripped.endswith("]")):
                # 检查括号是否闭合
                joined = "\n".join(json_lines)
                try:
                    json.loads(joined)
                    text = joined
                    break
                except json.JSONDecodeError:
                    pass
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"[KG] JSON 解析失败: {text[:1000]}")
        logger.warning(f"[KG] 解析错误: {e}")
        return {}


# ─── 实体抽取 ───────────────────────────────────
async def extract_from_chunk(chunk_text: str, max_retries: int = 2) -> dict:
    """对单个 chunk 调用 LLM 抽取实体和关系（带重试）"""
    p = _get_prompt("kg_extract")
    prompt = (p.get("user") or "").format(text=chunk_text[:3000])
    
    for attempt in range(max_retries + 1):
        try:
            resp = _llm_chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            if not resp or not resp.strip():
                if attempt < max_retries:
                    logger.warning(f"[KG] LLM返回空，重试 {attempt+1}/{max_retries}")
                    continue
                else:
                    return {"entities": [], "relations": []}
            
            logger.info(f"[KG] LLM原始输出: {resp[:300]}")
            result = _parse_llm_json(resp)
            entities = result.get("entities", [])
            relations = result.get("relations", [])
            logger.info(f"[KG] 抽取结果: entities={len(entities)}, relations={len(relations)}")
            # 过滤空名称
            entities = [e for e in entities if e.get("name", "").strip()]
            relations = [
                r for r in relations
                if r.get("subject", "").strip() and r.get("object", "").strip()
            ]
            return {"entities": entities, "relations": relations}
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"[KG] 抽取异常，重试 {attempt+1}/{max_retries}: {e}")
                continue
            else:
                logger.error(f"[KG] 抽取失败: {e}")
                return {"entities": [], "relations": []}


async def extract_and_store(
    kb_id: str,
    chunks: list[dict],
    db: Session,
    max_concurrent: int = 3,
) -> dict:
    """批量抽取并入库。chunks: [{"chunk_id": "...", "text": "..."}]"""
    # 合并相邻 chunk（每 3 个合并，约 1500 字）
    merged_texts = []
    merged_chunk_ids = []
    batch = []
    batch_ids = []
    for c in chunks:
        batch.append(c["text"])
        batch_ids.append(c["chunk_id"])
        if len(batch) >= 3:
            merged_texts.append("\n\n".join(batch))
            merged_chunk_ids.append(list(batch_ids))
            batch = []
            batch_ids = []
    if batch:
        merged_texts.append("\n\n".join(batch))
        merged_chunk_ids.append(list(batch_ids))

    # 并发控制
    sem = asyncio.Semaphore(max_concurrent)
    all_entities = []
    all_relations = []

    async def do_extract(i, text, chunk_ids):
        async with sem:
            result = await extract_from_chunk(text)
            return i, result, chunk_ids

    tasks = [do_extract(i, t, merged_chunk_ids[i]) for i, t in enumerate(merged_texts)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            logger.error(f"[KG] 批量抽取异常: {res}")
            continue
        _, result, chunk_ids = res
        for ent in result["entities"]:
            ent["_chunk_ids"] = chunk_ids
            all_entities.append(ent)
        for rel in result["relations"]:
            rel["_chunk_id"] = chunk_ids[0] if chunk_ids else ""
            all_relations.append(rel)

    # 入库
    stats = await _store_entities_relations(kb_id, all_entities, all_relations, db)
    return stats


async def _store_entities_relations(
    kb_id: str,
    raw_entities: list[dict],
    raw_relations: list[dict],
    db: Session,
) -> dict:
    """实体去重入库 + 关系去重入库"""
    # 1. 实体去重合并
    entity_map = {}  # name -> KGEntity
    for ent in raw_entities:
        name = ent["name"].strip()
        if name in entity_map:
            existing = entity_map[name]
            existing.frequency += 1
            # 合并 chunk_ids
            existing_ids = json.loads(existing.doc_chunk_ids)
            new_ids = ent.get("_chunk_ids", [])
            merged = list(set(existing_ids + new_ids))
            existing.doc_chunk_ids = json.dumps(merged)
            # 合并描述
            if not existing.description and ent.get("description"):
                existing.description = ent["description"]
        else:
            # 创建新实体
            entity_type = ent.get("type", "OTHER").upper()
            if entity_type not in EntityType.ALL:
                entity_type = EntityType.OTHER
            chunk_ids = ent.get("_chunk_ids", [])
            new_entity = KGEntity(
                kb_id=kb_id,
                name=name,
                entity_type=entity_type,
                description=ent.get("description", ""),
                doc_chunk_ids=json.dumps(chunk_ids),
                frequency=1,
            )
            db.add(new_entity)
            entity_map[name] = new_entity

    # flush 获取实体 ID
    db.flush()

    # 2. 为新实体生成 embedding
    new_entity_names = [e.name for e in entity_map.values() if e.embedding == "[]"]
    if new_entity_names:
        try:
            embeddings = embed_texts(new_entity_names)
            for name, emb in zip(new_entity_names, embeddings):
                if name in entity_map:
                    entity_map[name].embedding = json.dumps(emb)
        except Exception as e:
            logger.error(f"[KG] 实体向量化失败: {e}")

    # 3. 关系去重入库
    relation_set = set()  # (subject_id, predicate, object_id)
    new_relations = []
    for rel in raw_relations:
        subj_name = rel["subject"].strip()
        obj_name = rel["object"].strip()
        predicate = rel["predicate"].strip()

        if subj_name not in entity_map or obj_name not in entity_map:
            continue

        subj_id = entity_map[subj_name].id
        obj_id = entity_map[obj_name].id

        key = (subj_id, predicate, obj_id)
        if key in relation_set:
            continue
        relation_set.add(key)

        # 查数据库是否已存在
        existing = db.query(KGRelation).filter(
            KGRelation.kb_id == kb_id,
            KGRelation.subject_id == subj_id,
            KGRelation.predicate == predicate,
            KGRelation.object_id == obj_id,
        ).first()

        if not existing:
            new_rel = KGRelation(
                kb_id=kb_id,
                subject_id=subj_id,
                predicate=predicate,
                object_id=obj_id,
                doc_chunk_id=rel.get("_chunk_id", ""),
                confidence=0.8,
            )
            db.add(new_rel)
            new_relations.append(new_rel)

    db.commit()

    stats = {
        "entities_total": len(entity_map),
        "relations_total": len(new_relations),
    }
    logger.info(f"[KG] 图谱构建完成: {stats}")
    return stats


# ─── 图谱检索 ───────────────────────────────────
async def recognize_entities(question: str) -> list[dict]:
    """从用户问题中识别实体"""
    p = _get_prompt("kg_entity_recognize")
    prompt = (p.get("user") or "").format(question=question)
    try:
        resp = _llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        result = _parse_llm_json(resp)
        if isinstance(result, list):
            return [e for e in result if e.get("name", "").strip()]
        return []
    except Exception as e:
        logger.error(f"[KG] 实体识别失败: {e}")
        return []


def search_entity_exact(name: str, kb_id: str = None, db: Session = None) -> list[KGEntity]:
    """精确匹配 + 模糊匹配实体"""
    q = db.query(KGEntity)
    if kb_id:
        q = q.filter(KGEntity.kb_id == kb_id)
    # 精确匹配优先
    exact = q.filter(KGEntity.name == name).all()
    if exact:
        return exact
    # 模糊匹配
    fuzzy = q.filter(KGEntity.name.contains(name)).limit(10).all()
    return fuzzy


def search_entity_vector(query: str, kb_id: str = None, db: Session = None, top_k: int = 5, threshold: float = 0.75) -> list[tuple[KGEntity, float]]:
    """向量相似度匹配实体"""
    try:
        query_emb = embed_texts([query])[0]
    except Exception:
        return []

    q = db.query(KGEntity)
    if kb_id:
        q = q.filter(KGEntity.kb_id == kb_id)

    candidates = q.filter(KGEntity.embedding != "[]").all()
    scored = []
    for entity in candidates:
        try:
            ent_emb = json.loads(entity.embedding)
            # 余弦相似度
            dot = sum(a * b for a, b in zip(query_emb, ent_emb))
            norm_a = sum(a * a for a in query_emb) ** 0.5
            norm_b = sum(b * b for b in ent_emb) ** 0.5
            if norm_a > 0 and norm_b > 0:
                sim = dot / (norm_a * norm_b)
                if sim >= threshold:
                    scored.append((entity, sim))
        except Exception:
            continue

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def expand_relations(
    entity_ids: list[str],
    kb_id: str = None,
    hops: int = 1,
    db: Session = None,
    max_neighbors: int = 10,
) -> dict:
    """关系扩展（1-2 跳），返回节点和边"""
    nodes = {}  # id -> KGEntity
    edges = []  # KGRelation list
    visited_entity_ids = set()
    to_expand = list(entity_ids)

    for hop in range(hops):
        if not to_expand:
            break
        next_expand = []
        q = db.query(KGRelation).filter(
            or_(
                KGRelation.subject_id.in_(to_expand),
                KGRelation.object_id.in_(to_expand),
            )
        )
        if kb_id:
            q = q.filter(KGRelation.kb_id == kb_id)
        q = q.limit(max_neighbors * len(to_expand))

        relations = q.all()
        for rel in relations:
            edges.append(rel)
            for eid in [rel.subject_id, rel.object_id]:
                if eid not in visited_entity_ids:
                    visited_entity_ids.add(eid)
                    next_expand.append(eid)
                    entity = db.query(KGEntity).get(eid)
                    if entity:
                        nodes[eid] = entity
        to_expand = next_expand

    # 加入起始实体
    for eid in entity_ids:
        if eid not in nodes:
            entity = db.query(KGEntity).get(eid)
            if entity:
                nodes[eid] = entity

    return {"nodes": list(nodes.values()), "edges": edges}


def kg_search(
    entity_name: str,
    kb_id: str = None,
    hops: int = 1,
    db: Session = None,
) -> dict:
    """图谱检索入口：精确/模糊匹配 → 向量扩展 → 关系扩展"""
    # 1. 精确/模糊匹配
    matched = search_entity_exact(entity_name, kb_id, db)

    # 2. 向量扩展（如果精确匹配不足）
    if len(matched) < 3:
        vector_matches = search_entity_vector(entity_name, kb_id, db, top_k=5)
        existing_ids = {e.id for e in matched}
        for entity, score in vector_matches:
            if entity.id not in existing_ids:
                matched.append(entity)
                existing_ids.add(entity.id)

    if not matched:
        return {"nodes": [], "edges": [], "matched_entities": []}

    # 3. 关系扩展
    entity_ids = [e.id for e in matched]
    result = expand_relations(entity_ids, kb_id, hops, db)

    return {
        "nodes": result["nodes"],
        "edges": result["edges"],
        "matched_entities": matched,
    }


def kg_search_to_text(result: dict) -> str:
    """将图谱检索结果转为 LLM 可读的自然语言文本"""
    if not result["matched_entities"]:
        return ""

    lines = ["【知识图谱信息】"]

    # 实体信息
    lines.append("\n相关实体：")
    for entity in result["nodes"]:
        type_label = EntityType.LABELS.get(entity.entity_type, "其他")
        desc = f" — {entity.description}" if entity.description else ""
        lines.append(f"- {entity.name}（{type_label}）{desc}")

    # 关系链路
    if result["edges"]:
        lines.append("\n关系链路：")
        for rel in result["edges"]:
            lines.append(f"- {rel.subject.name} —[{rel.predicate}]→ {rel.object_.name}")

    return "\n".join(lines)


# ─── 统计 ───────────────────────────────────────
def get_kg_stats(kb_id: str = None, db: Session = None) -> dict:
    """图谱统计"""
    entity_q = db.query(KGEntity)
    relation_q = db.query(KGRelation)
    if kb_id:
        entity_q = entity_q.filter(KGEntity.kb_id == kb_id)
        relation_q = relation_q.filter(KGRelation.kb_id == kb_id)

    entity_count = entity_q.count()
    relation_count = relation_q.count()

    # 按类型分布
    type_dist = (
        entity_q.with_entities(KGEntity.entity_type, func.count(KGEntity.id))
        .group_by(KGEntity.entity_type)
        .all()
    )
    type_distribution = {t: c for t, c in type_dist}

    # Top 高频实体
    top_entities = (
        entity_q.order_by(KGEntity.frequency.desc())
        .limit(10)
        .all()
    )

    # 覆盖文档数
    all_chunk_ids = set()
    for entity in entity_q.all():
        try:
            ids = json.loads(entity.doc_chunk_ids)
            all_chunk_ids.update(ids)
        except Exception:
            pass

    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "type_distribution": type_distribution,
        "top_entities": [e.to_dict() for e in top_entities],
        "chunk_coverage": len(all_chunk_ids),
    }


# ─── 重建图谱 ───────────────────────────────────
def rebuild_graph(kb_id: str, db: Session):
    """删除某知识库的全部图谱数据"""
    db.query(KGRelation).filter(KGRelation.kb_id == kb_id).delete()
    db.query(KGEntity).filter(KGEntity.kb_id == kb_id).delete()
    db.commit()
    logger.info(f"[KG] 已清除 KB={kb_id} 的图谱数据")


def delete_entity(entity_id: str, db: Session):
    """删除实体（级联删除关联关系）"""
    # SQLAlchemy cascade 会自动处理，但显式删除更安全
    db.query(KGRelation).filter(
        or_(
            KGRelation.subject_id == entity_id,
            KGRelation.object_id == entity_id,
        )
    ).delete()
    db.query(KGEntity).filter(KGEntity.id == entity_id).delete()
    db.commit()


def delete_relation(relation_id: str, db: Session):
    """删除单条关系"""
    db.query(KGRelation).filter(KGRelation.id == relation_id).delete()
    db.commit()


def update_entity(entity_id: str, data: dict, db: Session) -> KGEntity:
    """编辑实体"""
    entity = db.query(KGEntity).get(entity_id)
    if not entity:
        raise ValueError(f"实体不存在: {entity_id}")
    for key in ["name", "entity_type", "description"]:
        if key in data:
            setattr(entity, key, data[key])
    db.commit()
    db.refresh(entity)
    return entity
