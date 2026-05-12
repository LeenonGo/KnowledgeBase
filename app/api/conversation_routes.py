"""对话历史 & 用户反馈 API"""

import json

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import now_cst
from app.models.models import Conversation, ConversationTurn, QAFeedback
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api", tags=["对话"])



# ─── 会话管理 ────────────────────────────────────

@router.get("/conversations")
async def list_conversations(conv_type: str = None, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """获取当前用户的对话列表"""
    q = db.query(Conversation).filter(
        Conversation.user_id == user["sub"],
        Conversation.status == "active",
    )
    if conv_type in ("rag", "agent"):
        q = q.filter(Conversation.conv_type == conv_type)
    convs = q.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc()).all()
    return [{
        "id": c.id, "title": c.title, "conv_type": c.conv_type,
        "is_pinned": bool(c.is_pinned),
        "tags": json.loads(c.tags) if c.tags else [],
        "created_at": str(c.created_at), "updated_at": str(c.updated_at),
    } for c in convs]


@router.post("/conversations")
async def create_conversation(data: dict = None,
                               db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """创建新对话"""
    _d = data or {}
    conv_type = _d.get("type", "rag")
    if conv_type not in ("rag", "agent"):
        conv_type = "rag"
    conv = Conversation(
        user_id=user["sub"],
        title=_d.get("title", "新对话"),
        conv_type=conv_type,
    )
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title, "conv_type": conv.conv_type}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str,
                              db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """删除对话（级联删除轮次和反馈）"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")

    # 级联删除：反馈 → 轮次 → 对话
    turn_ids = [t.id for t in db.query(ConversationTurn.id).filter(
        ConversationTurn.conversation_id == conv_id
    ).all()]
    if turn_ids:
        db.query(QAFeedback).filter(QAFeedback.turn_id.in_(turn_ids)).delete(synchronize_session=False)
        db.query(ConversationTurn).filter(ConversationTurn.conversation_id == conv_id).delete(synchronize_session=False)

    db.delete(conv)
    db.commit()
    return {"message": "已删除"}


# ─── 对话轮次 ────────────────────────────────────

@router.get("/conversations/{conv_id}/turns")
async def get_conversation_turns(conv_id: str,
                                 db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """获取对话的所有轮次"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")

    turns = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conv_id,
    ).order_by(ConversationTurn.created_at.asc()).all()

    items = []
    for t in turns:
        item = {
            "id": t.id, "role": t.role, "content": t.content,
            "created_at": str(t.created_at),
        }
        if t.sources:
            try:
                item["sources"] = json.loads(t.sources)
            except (json.JSONDecodeError, TypeError):
                item["sources"] = []
        items.append(item)

    return {"conversation_id": conv_id, "title": conv.title, "turns": items}


@router.post("/conversations/{conv_id}/turns")
async def add_conversation_turn(conv_id: str, data: dict,
                                db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """添加对话轮次"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")

    turn = ConversationTurn(
        conversation_id=conv_id,
        role=data.get("role", "user"),
        content=data.get("content", ""),
        sources=json.dumps(data.get("sources", []), ensure_ascii=False) if data.get("sources") else "",
        model=data.get("model", ""),
        latency_ms=data.get("latency_ms", 0),
        confidence=data.get("confidence", 0.0),
    )
    db.add(turn)

    # 更新对话时间 & 标题（首条用户消息作为标题）
    conv.updated_at = now_cst()
    if data.get("role") == "user" and conv.title in ("新对话", "Agent 对话"):
        raw_title = data.get("content", "")
        conv.title = raw_title[:50] + ("..." if len(raw_title) > 50 else "")
    db.commit()

    return {"id": turn.id, "role": turn.role}


# ─── 对话管理增强 ────────────────────────────────

@router.put("/conversations/{conv_id}/pin")
async def toggle_pin(conv_id: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """置顶/取消置顶对话"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")
    conv.is_pinned = not conv.is_pinned
    db.commit()
    return {"id": conv.id, "is_pinned": bool(conv.is_pinned)}


@router.put("/conversations/{conv_id}/tags")
async def update_tags(conv_id: str, data: dict, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """更新对话标签"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        raise HTTPException(400, "tags 必须是数组")
    conv.tags = json.dumps(tags[:10], ensure_ascii=False)  # 最多 10 个标签
    db.commit()
    return {"id": conv.id, "tags": tags}


@router.get("/conversations/{conv_id}/export")
async def export_conversation(conv_id: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """导出对话为 Markdown"""
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user["sub"],
    ).first()
    if not conv:
        raise HTTPException(404, "对话不存在")

    turns = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conv_id,
    ).order_by(ConversationTurn.created_at.asc()).all()

    lines = [f"# {conv.title}", "", f"创建时间: {conv.created_at}", ""]
    for t in turns:
        role = "👤 用户" if t.role == "user" else "🤖 助手"
        lines.append(f"## {role}")
        lines.append("")
        lines.append(t.content)
        lines.append("")
        lines.append("---")
        lines.append("")

    md_content = "\n".join(lines)
    log_audit(db, user, "export", conv.title[:50], f"导出对话 {conv_id}", "success", "")
    from fastapi.responses import Response
    from urllib.parse import quote
    safe_name = quote(conv.title[:30] or '对话') + '.md'
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


# ─── 用户反馈 ────────────────────────────────────

@router.post("/feedback")
async def submit_feedback(data: dict, request: Request,
                          db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """提交问答反馈（👍👎）"""
    turn_id = data.get("turn_id")
    rating = data.get("rating")  # "up" or "down"
    comment = data.get("comment", "")

    if not turn_id or rating not in ("up", "down"):
        raise HTTPException(400, "参数错误")

    turn = db.query(ConversationTurn).filter(ConversationTurn.id == turn_id).first()
    if not turn:
        raise HTTPException(404, "对话轮次不存在")

    # 更新已有反馈或创建新反馈
    existing = db.query(QAFeedback).filter(
        QAFeedback.turn_id == turn_id,
        QAFeedback.user_id == user["sub"],
    ).first()

    if existing:
        existing.rating = rating
        existing.comment = comment
    else:
        fb = QAFeedback(
            turn_id=turn_id, user_id=user["sub"],
            rating=rating, comment=comment,
        )
        db.add(fb)
    db.commit()

    return {"message": "反馈已提交"}


@router.get("/feedback")
async def list_feedback(rating: str = None, page: int = 1, page_size: int = 20,
                        db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """获取反馈列表（管理员用） — 用子查询批量取回答和问题，消除 N+1"""
    from sqlalchemy import func as sa_func

    q = db.query(QAFeedback)
    if rating:
        q = q.filter(QAFeedback.rating == rating)

    total = q.count()
    feedbacks = q.order_by(QAFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    if not feedbacks:
        return {"total": total, "items": []}

    # 批量查 assistant turn
    turn_ids = [fb.turn_id for fb in feedbacks]
    assistant_turns = db.query(ConversationTurn).filter(
        ConversationTurn.id.in_(turn_ids)
    ).all()
    turn_map = {t.id: t for t in assistant_turns}

    # 批量查对应的 user turn（每个对话中在 assistant turn 之前最近的一条）
    conv_ids = list({t.conversation_id for t in assistant_turns}) if assistant_turns else []
    user_turn_map = {}
    if conv_ids:
        # 用子查询：对每个 conv_id + assistant turn 时间，找最近的 user turn
        for at in assistant_turns:
            prev_user = db.query(ConversationTurn).filter(
                ConversationTurn.conversation_id == at.conversation_id,
                ConversationTurn.role == "user",
                ConversationTurn.created_at <= at.created_at,
            ).order_by(ConversationTurn.created_at.desc()).first()
            if prev_user:
                user_turn_map[at.id] = prev_user.content

    result = []
    for fb in feedbacks:
        at = turn_map.get(fb.turn_id)
        result.append({
            "id": fb.id, "turn_id": fb.turn_id,
            "rating": fb.rating, "comment": fb.comment,
            "user_id": fb.user_id,
            "question": user_turn_map.get(fb.turn_id, ""),
            "answer": at.content if at else "",
            "created_at": str(fb.created_at),
        })

    return {"total": total, "items": result}
