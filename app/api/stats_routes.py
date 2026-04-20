"""统计 API — 仪表盘 + 质量监控数据"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.models import KnowledgeBase, Document, AuditLog, QAFeedback, ConversationTurn
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["统计"])

_CST = timezone(timedelta(hours=8))


@router.get("/stats/dashboard")
async def get_dashboard_stats(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """仪表盘统计数据"""
    # 知识库数
    kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.status != "deleted").count()

    # 文档数
    doc_count = db.query(Document).filter(Document.status != "deleted").count()

    # 总 chunks
    chunks = db.query(func.coalesce(func.sum(Document.chunk_count), 0)).filter(
        Document.status != "deleted"
    ).scalar()

    # 今日问答次数
    today_start = datetime.now(_CST).replace(hour=0, minute=0, second=0, microsecond=0)
    today_queries = db.query(AuditLog).filter(
        AuditLog.action == "query",
        AuditLog.created_at >= today_start,
    ).count()

    # 近 7 天每日问答次数
    daily_queries = []
    for i in range(6, -1, -1):
        day = today_start - timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = db.query(AuditLog).filter(
            AuditLog.action == "query",
            AuditLog.created_at >= day,
            AuditLog.created_at < next_day,
        ).count()
        daily_queries.append({
            "date": day.strftime("%m-%d"),
            "count": count,
        })

    # 总反馈数 & 点赞率
    total_feedback = db.query(QAFeedback).count()
    up_count = db.query(QAFeedback).filter(QAFeedback.rating == "up").count()
    like_rate = round(up_count / total_feedback * 100, 1) if total_feedback > 0 else 0

    return {
        "kb_count": kb_count,
        "doc_count": doc_count,
        "chunks_count": int(chunks),
        "today_queries": today_queries,
        "daily_queries": daily_queries,
        "total_feedback": total_feedback,
        "like_rate": like_rate,
    }


@router.get("/stats/quality")
async def get_quality_stats(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """质量监控统计数据"""
    # 总反馈数
    total_feedback = db.query(QAFeedback).count()

    # 点踩数 & 差评率
    down_count = db.query(QAFeedback).filter(QAFeedback.rating == "down").count()
    down_rate = round(down_count / total_feedback * 100, 1) if total_feedback > 0 else 0

    # 平均延迟
    avg_latency = db.query(func.avg(ConversationTurn.latency_ms)).filter(
        ConversationTurn.role == "assistant",
        ConversationTurn.latency_ms > 0,
    ).scalar()
    avg_latency_s = round((avg_latency or 0) / 1000, 2)

    # 今日问答数
    today_start = datetime.now(_CST).replace(hour=0, minute=0, second=0, microsecond=0)
    today_queries = db.query(AuditLog).filter(
        AuditLog.action == "query",
        AuditLog.created_at >= today_start,
    ).count()

    # 未命中数（拒答）& 无结果率
    no_result = db.query(AuditLog).filter(
        AuditLog.action == "query",
        AuditLog.detail.like("%未命中%"),
    ).count()
    total_queries = db.query(AuditLog).filter(AuditLog.action == "query").count()
    no_result_rate = round(no_result / total_queries * 100, 1) if total_queries > 0 else 0

    return {
        "total_feedback": total_feedback,
        "down_count": down_count,
        "down_rate": down_rate,
        "avg_latency": avg_latency_s,
        "today_queries": today_queries,
        "no_result_rate": no_result_rate,
    }
