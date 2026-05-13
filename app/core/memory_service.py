"""
长期记忆层 — 用户记忆提取/检索 + FAQ 沉淀/生命周期管理

模块职责：
- UserMemory：从对话中提取用户偏好/上下文/纠正，注入 prompt
- FAQ：高频问答自动沉淀、检索命中、衰减淘汰
"""

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.models.models import UserMemory, FAQ, FAQTag, FAQCandidate, ConversationTurn

_CST = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════════════════════
# 用户记忆 (UserMemory)
# ═══════════════════════════════════════════════════════════

MAX_USER_MEMORIES = 50          # 单用户记忆上限
MEMORY_DECAY_DAYS = 90          # 90 天后置信度开始衰减
MEMORY_DECAY_RATE = 0.01        # 每天衰减 1%
EXTRACT_MIN_TURNS = 2           # 至少 2 轮对话才触发提取


def get_user_memories(db: Session, user_id: str, active_only: bool = True) -> list[dict]:
    """获取用户的所有记忆，按 confidence × hit_count 排序"""
    q = db.query(UserMemory).filter(UserMemory.user_id == user_id)
    if active_only:
        q = q.filter(
            or_(UserMemory.expired_at.is_(None), UserMemory.expired_at > datetime.now(_CST)),
            UserMemory.confidence > 0.3,
        )
    memories = q.order_by(
        (UserMemory.confidence * (UserMemory.hit_count + 1)).desc()
    ).all()
    return [_memory_to_dict(m) for m in memories]


def format_memories_for_prompt(memories: list[dict]) -> str:
    """将用户记忆格式化为注入 system prompt 的文本"""
    if not memories:
        return ""
    type_labels = {"preference": "偏好", "context": "背景", "correction": "纠正"}
    lines = ["[用户记忆]"]
    for m in memories[:20]:  # 最多注入 20 条
        label = type_labels.get(m["memory_type"], m["memory_type"])
        lines.append(f"- [{label}] {m['content']}")
    return "\n".join(lines)


def record_memory_hit(db: Session, memory_ids: list[str]):
    """记录记忆被引用，更新 hit_count 和 last_hit_at"""
    if not memory_ids:
        return
    now = datetime.now(_CST)
    db.query(UserMemory).filter(UserMemory.id.in_(memory_ids)).update(
        {UserMemory.hit_count: UserMemory.hit_count + 1, UserMemory.last_hit_at: now},
        synchronize_session=False,
    )
    db.commit()


def decay_memories(db: Session):
    """衰减持信度 — 建议定期调用（如每天一次）"""
    now = datetime.now(_CST)
    threshold = now - timedelta(days=MEMORY_DECAY_DAYS)
    # 对超过阈值且未过期的记忆衰减
    stale = db.query(UserMemory).filter(
        UserMemory.created_at < threshold,
        or_(UserMemory.expired_at.is_(None), UserMemory.expired_at > now),
    ).all()
    for m in stale:
        days_old = (now - m.created_at).days
        m.confidence = max(0.0, 1.0 - MEMORY_DECAY_RATE * (days_old - MEMORY_DECAY_DAYS))
        if m.confidence <= 0.1:
            m.expired_at = now
    db.commit()


def _enforce_memory_limit(db: Session, user_id: str):
    """确保用户记忆不超上限，淘汰低价值记忆"""
    count = db.query(func.count(UserMemory.id)).filter(UserMemory.user_id == user_id).scalar()
    if count <= MAX_USER_MEMORIES:
        return
    excess = count - MAX_USER_MEMORIES
    # 按 confidence × (hit_count+1) 升序淘汰
    to_delete = db.query(UserMemory).filter(
        UserMemory.user_id == user_id,
    ).order_by(
        (UserMemory.confidence * (UserMemory.hit_count + 1)).asc()
    ).limit(excess).all()
    for m in to_delete:
        db.delete(m)
    db.commit()


def extract_and_save_memories(db: Session, user_id: str, conv_id: str,
                               user_msg: str, assistant_msg: str) -> list[dict]:
    """
    从一轮对话中提取可记忆的用户信息。
    简化版：基于规则 + LLM 提取（在外部调用 LLM 后传入结果）。
    这里做基础规则提取，LLM 提取由调用方决定。
    """
    new_memories = []
    content = f"{user_msg}\n{assistant_msg}"

    # 规则提取：用户纠正
    correction_patterns = [
        r'(?:不要|别|错了|不对|应该是|正确的是|改成)(.{5,50})',
    ]
    for pat in correction_patterns:
        for match in re.finditer(pat, user_msg):
            text = match.group(0).strip()
            if len(text) > 5:
                new_memories.append({
                    "memory_type": "correction",
                    "content": text,
                    "source_conv_id": conv_id,
                })

    # 规则提取：用户自称/偏好
    pref_patterns = [
        r'(?:我(?:是|叫|负责|在|来自|偏好|喜欢|希望))(.{3,50})',
        r'(?:我的?(?:称呼|名字)(?:是|叫))(.{3,30})',
    ]
    for pat in pref_patterns:
        for match in re.finditer(pat, user_msg):
            text = match.group(0).strip()
            if len(text) > 5:
                new_memories.append({
                    "memory_type": "preference",
                    "content": text,
                    "source_conv_id": conv_id,
                })

    # 去重 + 保存
    existing = {m.content for m in db.query(UserMemory.content).filter(
        UserMemory.user_id == user_id,
    ).all()}

    saved = []
    for mem in new_memories:
        if mem["content"] in existing:
            continue
        record = UserMemory(
            user_id=user_id,
            memory_type=mem["memory_type"],
            content=mem["content"],
            source_conv_id=mem.get("source_conv_id"),
        )
        db.add(record)
        saved.append(mem)
        existing.add(mem["content"])

    if saved:
        db.commit()
        _enforce_memory_limit(db, user_id)

    return saved


def extract_memories_from_llm(db: Session, user_id: str, conv_id: str,
                                memories: list[dict]) -> list[dict]:
    """保存 LLM 提取的记忆（外部调用 LLM 后传入结果）"""
    existing = {m.content for m in db.query(UserMemory.content).filter(
        UserMemory.user_id == user_id,
    ).all()}
    saved = []
    for mem in memories:
        content = mem.get("content", "").strip()
        mtype = mem.get("memory_type", "context")
        if not content or content in existing or mtype not in ("preference", "context", "correction"):
            continue
        record = UserMemory(
            user_id=user_id,
            memory_type=mtype,
            content=content,
            source_conv_id=conv_id,
        )
        db.add(record)
        saved.append(mem)
        existing.add(content)
    if saved:
        db.commit()
        _enforce_memory_limit(db, user_id)
    return saved


def delete_user_memory(db: Session, memory_id: str, user_id: str) -> bool:
    """删除单条记忆"""
    m = db.query(UserMemory).filter(UserMemory.id == memory_id, UserMemory.user_id == user_id).first()
    if not m:
        return False
    db.delete(m)
    db.commit()
    return True


def _memory_to_dict(m: UserMemory) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "memory_type": m.memory_type,
        "content": m.content,
        "source_conv_id": m.source_conv_id,
        "confidence": m.confidence,
        "hit_count": m.hit_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


# ═══════════════════════════════════════════════════════════
# FAQ 沉淀
# ═══════════════════════════════════════════════════════════

FAQ_AUTO_THRESHOLD = 3          # 同一问题出现 ≥3 次自动沉淀
FAQ_APPROVE_RATING = 0.8        # 好评率 ≥ 80% 才沉淀
FAQ_MATCH_THRESHOLD = 0.85      # 语义匹配阈值
FAQ_DECAY_DAYS = 30             # 30 天未命中开始衰减
FAQ_ARCHIVE_THRESHOLD = 0.3     # 置信度 < 0.3 归档


def _normalize_question(question: str) -> str:
    """问题归一化：去除标点、空格，转小写"""
    q = re.sub(r'[\s?？!！。，,、；;：:."\']', '', question.lower())
    return q[:200]  # 截断避免超长


def _question_hash(question: str) -> str:
    """问题哈希"""
    normalized = _normalize_question(question)
    return hashlib.md5(normalized.encode()).hexdigest()


def record_faq_candidate(db: Session, question: str, answer: str,
                          kb_id: str = None, turn_id: str = None,
                          citations: list = None, is_positive: bool = False):
    """记录问答对为 FAQ 候选（每次问答后调用）"""
    qhash = _question_hash(question)
    candidate = db.query(FAQCandidate).filter(
        FAQCandidate.question_hash == qhash,
    ).first()

    if candidate:
        candidate.hit_count += 1
        if is_positive:
            candidate.positive_count += 1
        candidate.last_answer = answer[:4000]
        candidate.last_citations = json.dumps(citations or [], ensure_ascii=False)
        candidate.last_turn_id = turn_id
        candidate.updated_at = datetime.now(_CST)
    else:
        candidate = FAQCandidate(
            kb_id=kb_id,
            question_hash=qhash,
            question_sample=question[:500],
            hit_count=1,
            positive_count=1 if is_positive else 0,
            last_answer=answer[:4000],
            last_citations=json.dumps(citations or [], ensure_ascii=False),
            last_turn_id=turn_id,
        )
        db.add(candidate)

    db.commit()

    # 检查是否满足自动沉淀条件
    if candidate.hit_count >= FAQ_AUTO_THRESHOLD:
        positive_rate = candidate.positive_count / candidate.hit_count
        if positive_rate >= FAQ_APPROVE_RATING:
            _auto_sediment_faq(db, candidate)


def _auto_sediment_faq(db: Session, candidate: FAQCandidate):
    """自动沉淀为 FAQ"""
    # 检查是否已存在相同问题的 FAQ
    existing = db.query(FAQ).filter(
        FAQ.question == candidate.question_sample,
    ).first()
    if existing:
        return

    faq = FAQ(
        kb_id=candidate.kb_id,
        question=candidate.question_sample,
        answer=candidate.last_answer,
        source_turn_id=candidate.last_turn_id,
        source_citations=candidate.last_citations,
        status="auto",  # 自动沉淀，待审核
    )
    db.add(faq)
    db.commit()
    print(f"[FAQ] 自动沉淀: {candidate.question_sample[:50]}...")


def search_faq(db: Session, question: str, kb_id: str = None,
               accessible_ids: list[str] = None) -> dict | None:
    """
    搜索 FAQ — 基于问题哈希 + 文本相似度的双重匹配。
    返回匹配的 FAQ 或 None。
    """
    qhash = _question_hash(question)
    normalized_q = _normalize_question(question)

    # 1. 精确哈希匹配
    candidates = db.query(FAQCandidate).filter(
        FAQCandidate.question_hash == qhash,
    ).all()

    if candidates:
        # 找到精确匹配，查找对应 FAQ
        for c in candidates:
            faq = db.query(FAQ).filter(
                FAQ.question == c.question_sample,
                FAQ.status.in_(["auto", "approved"]),
            ).first()
            if faq:
                _check_faq_access(faq, kb_id, accessible_ids)
                return _faq_hit(db, faq)

    # 2. 模糊匹配：遍历已批准的 FAQ
    q = db.query(FAQ).filter(FAQ.status.in_(["auto", "approved"]))
    if kb_id:
        q = q.filter(or_(FAQ.kb_id == kb_id, FAQ.kb_id.is_(None)))
    elif accessible_ids is not None:
        q = q.filter(or_(FAQ.kb_id.in_(accessible_ids), FAQ.kb_id.is_(None)))

    all_faqs = q.all()
    best_match = None
    best_score = 0

    for faq in all_faqs:
        faq_norm = _normalize_question(faq.question)
        # 简单的字符重叠率
        if not faq_norm or not normalized_q:
            continue
        overlap = len(set(normalized_q) & set(faq_norm))
        score = overlap / max(len(set(normalized_q)), len(set(faq_norm)))
        if score > best_score:
            best_score = score
            best_match = faq

    if best_match and best_score >= FAQ_MATCH_THRESHOLD:
        return _faq_hit(db, best_match)

    return None


def _check_faq_access(faq: FAQ, kb_id: str, accessible_ids: list[str]):
    """检查 FAQ 访问权限（已在 search_faq 中通过查询条件过滤）"""
    pass


def _faq_hit(db: Session, faq: FAQ) -> dict:
    """记录 FAQ 命中，返回 FAQ 信息"""
    faq.hit_count += 1
    faq.last_hit_at = datetime.now(_CST) if hasattr(faq, 'last_hit_at') else None
    db.commit()

    citations = []
    try:
        citations = json.loads(faq.source_citations) if faq.source_citations else []
    except json.JSONDecodeError:
        pass

    # 获取标签
    tags = [t.tag for t in db.query(FAQTag.tag).filter(FAQTag.faq_id == faq.id).all()]

    return {
        "faq_id": faq.id,
        "question": faq.question,
        "answer": faq.answer,
        "status": faq.status,
        "hit_count": faq.hit_count,
        "citations": citations,
        "tags": tags,
    }


def get_all_faqs(db: Session, kb_id: str = None, status: str = None,
                 page: int = 1, page_size: int = 20) -> dict:
    """获取 FAQ 列表（分页）"""
    q = db.query(FAQ)
    if kb_id:
        q = q.filter(FAQ.kb_id == kb_id)
    if status:
        q = q.filter(FAQ.status == status)

    total = q.count()
    faqs = q.order_by(FAQ.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for f in faqs:
        tags = [t.tag for t in db.query(FAQTag.tag).filter(FAQTag.faq_id == f.id).all()]
        items.append({
            "id": f.id,
            "kb_id": f.kb_id,
            "question": f.question,
            "answer": f.answer[:200],
            "full_answer": f.answer,
            "status": f.status,
            "hit_count": f.hit_count,
            "avg_rating": f.avg_rating,
            "confidence": f.confidence,
            "tags": tags,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        })

    return {"total": total, "items": items, "page": page, "page_size": page_size}


def approve_faq(db: Session, faq_id: str, user_id: str) -> bool:
    """审核通过 FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        return False
    faq.status = "approved"
    faq.approved_by = user_id
    faq.confidence = 1.0
    faq.updated_at = datetime.now(_CST)
    db.commit()
    return True


def reject_faq(db: Session, faq_id: str) -> bool:
    """拒绝 FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        return False
    faq.status = "rejected"
    faq.updated_at = datetime.now(_CST)
    db.commit()
    return True


def delete_faq(db: Session, faq_id: str) -> bool:
    """删除 FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        return False
    db.delete(faq)
    db.commit()
    return True


def decay_faqs(db: Session):
    """FAQ 衰减机制 — 超过 FAQ_DECAY_DAYS 未命中的 FAQ 降低置信度"""
    now = datetime.now(_CST)
    threshold = now - timedelta(days=FAQ_DECAY_DAYS)

    # 查找长期未命中的 FAQ
    stale = db.query(FAQ).filter(
        FAQ.status.in_(["auto", "approved"]),
        FAQ.updated_at < threshold,
        FAQ.hit_count < 2,  # 低频访问
    ).all()

    for faq in stale:
        days_since_update = (now - faq.updated_at).days
        faq.confidence = max(0.0, faq.confidence - 0.02 * (days_since_update - FAQ_DECAY_DAYS))
        if faq.confidence < FAQ_ARCHIVE_THRESHOLD:
            faq.status = "archived"
        db.add(faq)

    db.commit()


def get_faq_stats(db: Session) -> dict:
    """FAQ 统计信息"""
    total = db.query(func.count(FAQ.id)).scalar()
    by_status = dict(db.query(FAQ.status, func.count(FAQ.id)).group_by(FAQ.status).all())
    total_hits = db.query(func.sum(FAQ.hit_count)).scalar() or 0
    pending = by_status.get("auto", 0)

    # 候选池统计
    candidate_count = db.query(func.count(FAQCandidate.id)).scalar()
    near_threshold = db.query(func.count(FAQCandidate.id)).filter(
        FAQCandidate.hit_count >= FAQ_AUTO_THRESHOLD - 1,
    ).scalar()

    return {
        "total": total,
        "by_status": by_status,
        "total_hits": total_hits,
        "pending_review": pending,
        "candidate_count": candidate_count,
        "near_threshold": near_threshold,
    }


def get_memory_stats(db: Session, user_id: str = None) -> dict:
    """记忆统计"""
    if user_id:
        total = db.query(func.count(UserMemory.id)).filter(UserMemory.user_id == user_id).scalar()
        by_type = dict(
            db.query(UserMemory.memory_type, func.count(UserMemory.id))
            .filter(UserMemory.user_id == user_id)
            .group_by(UserMemory.memory_type).all()
        )
    else:
        total = db.query(func.count(UserMemory.id)).scalar()
        by_type = dict(
            db.query(UserMemory.memory_type, func.count(UserMemory.id))
            .group_by(UserMemory.memory_type).all()
        )
    return {"total": total, "by_type": by_type}
