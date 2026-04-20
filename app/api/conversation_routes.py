"""对话历史 & 用户反馈 API"""

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Conversation, ConversationTurn, QAFeedback, AuditLog
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["对话"])

_CST = timezone(timedelta(hours=8))


def _log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


# ─── 会话管理 ────────────────────────────────────

@router.get("/conversations")
async def list_conversations(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """获取当前用户的对话列表"""
    convs = db.query(Conversation).filter(
        Conversation.user_id == user["sub"],
        Conversation.status == "active",
    ).order_by(Conversation.updated_at.desc()).all()
    return [{
        "id": c.id, "title": c.title,
        "created_at": str(c.created_at), "updated_at": str(c.updated_at),
    } for c in convs]


@router.post("/conversations")
async def create_conversation(data: dict = None,
                               db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """创建新对话"""
    conv = Conversation(
        user_id=user["sub"],
        title=(data or {}).get("title", "新对话"),
    )
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title}


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
    conv.updated_at = datetime.now(_CST)
    if data.get("role") == "user" and conv.title == "新对话":
        conv.title = data.get("content", "")[:50]
    db.commit()

    return {"id": turn.id, "role": turn.role}


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
    """获取反馈列表（管理员用）"""
    q = db.query(QAFeedback)
    if rating:
        q = q.filter(QAFeedback.rating == rating)

    total = q.count()
    items = q.order_by(QAFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for fb in items:
        assistant_turn = db.query(ConversationTurn).filter(ConversationTurn.id == fb.turn_id).first()
        question = ""
        answer = ""
        if assistant_turn:
            answer = assistant_turn.content
            # 往前找同一对话中的用户提问
            user_turn = db.query(ConversationTurn).filter(
                ConversationTurn.conversation_id == assistant_turn.conversation_id,
                ConversationTurn.role == "user",
                ConversationTurn.created_at < assistant_turn.created_at,
            ).order_by(ConversationTurn.created_at.desc()).first()
            if user_turn:
                question = user_turn.content
        result.append({
            "id": fb.id, "turn_id": fb.turn_id,
            "rating": fb.rating, "comment": fb.comment,
            "user_id": fb.user_id,
            "question": question,
            "answer": answer,
            "created_at": str(fb.created_at),
        })

    return {"total": total, "items": result}
