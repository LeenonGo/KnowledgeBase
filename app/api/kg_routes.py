"""知识图谱 API 路由"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, require_kb_access, get_accessible_kb_ids
from app.models.kg_models import KGEntity, KGRelation, EntityType

router = APIRouter(prefix="/api/kg", tags=["知识图谱"])


# ─── 图谱数据查询 ─────────────────────────────────
@router.get("/{kb_id}/entities")
async def get_entities(
    kb_id: str,
    entity_type: Optional[str] = Query(None, description="实体类型筛选"),
    keyword: Optional[str] = Query(None, description="名称搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取实体列表（分页、筛选）"""
    require_kb_access(db, user, kb_id, "viewer")

    q = db.query(KGEntity).filter(KGEntity.kb_id == kb_id)
    if entity_type:
        q = q.filter(KGEntity.entity_type == entity_type)
    if keyword:
        q = q.filter(KGEntity.name.contains(keyword))

    total = q.count()
    entities = q.order_by(KGEntity.frequency.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "entities": [e.to_dict() for e in entities],
    }


@router.get("/{kb_id}/relations")
async def get_relations(
    kb_id: str,
    entity_id: Optional[str] = Query(None, description="关联实体 ID"),
    predicate: Optional[str] = Query(None, description="关系类型筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取关系列表（分页、筛选）"""
    require_kb_access(db, user, kb_id, "viewer")

    q = db.query(KGRelation).filter(KGRelation.kb_id == kb_id)
    if entity_id:
        from sqlalchemy import or_
        q = q.filter(or_(KGRelation.subject_id == entity_id, KGRelation.object_id == entity_id))
    if predicate:
        q = q.filter(KGRelation.predicate == predicate)

    total = q.count()
    relations = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "relations": [r.to_dict() for r in relations],
    }


@router.get("/{kb_id}/graph")
async def get_graph_data(
    kb_id: str,
    limit: int = Query(200, ge=1, le=1000, description="最大节点数"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取完整图谱数据（节点 + 边），供前端可视化"""
    require_kb_access(db, user, kb_id, "viewer")

    # 获取 Top 高频实体
    entities = (
        db.query(KGEntity)
        .filter(KGEntity.kb_id == kb_id)
        .order_by(KGEntity.frequency.desc())
        .limit(limit)
        .all()
    )

    entity_ids = {e.id for e in entities}

    # 获取关联关系
    from sqlalchemy import or_
    relations = db.query(KGRelation).filter(
        KGRelation.kb_id == kb_id,
        KGRelation.subject_id.in_(entity_ids),
        KGRelation.object_id.in_(entity_ids),
    ).all()

    # 构造 D3 力导向图数据格式
    nodes = []
    for e in entities:
        nodes.append({
            "id": e.id,
            "name": e.name,
            "type": e.entity_type,
            "type_label": EntityType.LABELS.get(e.entity_type, "其他"),
            "color": EntityType.COLORS.get(e.entity_type, "#95A5A6"),
            "description": e.description,
            "frequency": e.frequency,
        })

    edges = []
    for r in relations:
        edges.append({
            "id": r.id,
            "source": r.subject_id,
            "target": r.object_id,
            "label": r.predicate,
            "confidence": r.confidence,
        })

    # 统计
    total_entities = db.query(KGEntity).filter(KGEntity.kb_id == kb_id).count()
    total_relations = db.query(KGRelation).filter(KGRelation.kb_id == kb_id).count()

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "entity_count": total_entities,
            "relation_count": total_relations,
            "displayed_nodes": len(nodes),
            "displayed_edges": len(edges),
        },
    }


@router.get("/{kb_id}/search")
async def search_graph(
    kb_id: str,
    entity: str = Query(..., description="实体名称"),
    hops: int = Query(1, ge=1, le=2, description="关系跳数"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """图谱检索（实体名 + 跳数）"""
    require_kb_access(db, user, kb_id, "viewer")

    from app.core.kg_service import kg_search
    result = kg_search(entity, kb_id=kb_id, hops=hops, db=db)

    nodes = []
    for e in result["nodes"]:
        nodes.append({
            "id": e.id,
            "name": e.name,
            "type": e.entity_type,
            "type_label": EntityType.LABELS.get(e.entity_type, "其他"),
            "color": EntityType.COLORS.get(e.entity_type, "#95A5A6"),
            "description": e.description,
            "frequency": e.frequency,
        })

    edges = []
    for r in result["edges"]:
        edges.append({
            "id": r.id,
            "source": r.subject_id,
            "target": r.object_id,
            "label": r.predicate,
            "confidence": r.confidence,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "matched_entities": [e.name for e in result["matched_entities"]],
    }


@router.get("/{kb_id}/stats")
async def get_graph_stats(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """图谱统计"""
    require_kb_access(db, user, kb_id, "viewer")

    from app.core.kg_service import get_kg_stats
    return get_kg_stats(kb_id=kb_id, db=db)


@router.post("/{kb_id}/build")
async def build_graph(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从已有文档构建图谱（异步后台执行）"""
    import asyncio
    import threading
    require_kb_access(db, user, kb_id, "admin")

    from app.core.vectorstore import _collection
    from app.core.kg_service import extract_and_store

    # 获取该 KB 的所有 chunks
    results = _collection.get(where={"kb_id": kb_id})
    if not results["ids"]:
        return {"message": "该知识库没有文档数据"}

    chunks = [
        {"chunk_id": cid, "text": text}
        for cid, text in zip(results["ids"], results["documents"])
    ]

    # 异步执行抽取
    def _run_extract():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(
                extract_and_store(kb_id, chunks, db, max_concurrent=3)
            )
            print(f"[KG] 图谱构建完成: {stats}")
        except Exception as e:
            print(f"[KG] 图谱构建失败: {e}")
        finally:
            loop.close()

    t = threading.Thread(target=_run_extract, daemon=True)
    t.start()

    return {
        "message": f"图谱构建已启动，共 {len(chunks)} 个文本块，预计需要几分钟",
        "total_chunks": len(chunks),
    }


# ─── 图谱管理 ───────────────────────────────────
@router.post("/{kb_id}/rebuild")
async def rebuild_graph(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重建图谱（清除后需重新上传文档触发抽取）"""
    require_kb_access(db, user, kb_id, "admin")

    from app.core.kg_service import rebuild_graph as _rebuild
    _rebuild(kb_id, db)
    return {"message": "图谱数据已清除，请重新上传文档触发图谱构建"}


@router.delete("/{kb_id}/entity/{entity_id}")
async def delete_entity(
    kb_id: str,
    entity_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除实体（级联删除关联关系）"""
    require_kb_access(db, user, kb_id, "admin")

    from app.core.kg_service import delete_entity as _delete
    _delete(entity_id, db)
    return {"message": "实体已删除"}


@router.delete("/{kb_id}/relation/{relation_id}")
async def delete_relation(
    kb_id: str,
    relation_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除关系"""
    require_kb_access(db, user, kb_id, "admin")

    from app.core.kg_service import delete_relation as _delete
    _delete(relation_id, db)
    return {"message": "关系已删除"}


@router.put("/{kb_id}/entity/{entity_id}")
async def update_entity(
    kb_id: str,
    entity_id: str,
    data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑实体"""
    require_kb_access(db, user, kb_id, "admin")

    from app.core.kg_service import update_entity as _update
    entity = _update(entity_id, data, db)
    return entity.to_dict()
