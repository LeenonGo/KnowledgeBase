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


@router.get("/stats/kb-health")
async def get_kb_health_stats(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """知识库健康度统计"""
    from app.models.models import KnowledgeBase, Document
    from app.api.deps import get_accessible_kb_ids

    accessible_ids = get_accessible_kb_ids(db, user)
    if accessible_ids is None:
        kbs = db.query(KnowledgeBase).filter(KnowledgeBase.status != "deleted").all()
    elif not accessible_ids:
        return {"knowledge_bases": [], "overall": {}}
    else:
        kbs = db.query(KnowledgeBase).filter(
            KnowledgeBase.id.in_(accessible_ids), KnowledgeBase.status != "deleted"
        ).all()

    kb_stats = []
    total_docs = 0
    total_chunks = 0

    # 批量查询所有文档（避免 N+1）
    kb_ids = [kb.id for kb in kbs]
    all_docs = db.query(Document).filter(
        Document.kb_id.in_(kb_ids), Document.status.in_(["indexed", "active"])
    ).all() if kb_ids else []
    docs_by_kb = {}
    for d in all_docs:
        docs_by_kb.setdefault(d.kb_id, []).append(d)

    # 批量查询近 7 天审计日志
    seven_days_ago = datetime.now(_CST) - timedelta(days=7)
    all_logs = db.query(AuditLog).filter(
        AuditLog.action == "query", AuditLog.created_at >= seven_days_ago
    ).all() if kb_ids else []
    query_count_by_kb = {}
    for log in all_logs:
        detail = log.detail or ""
        for kid in kb_ids:
            if f"kb={kid}" in detail:
                query_count_by_kb[kid] = query_count_by_kb.get(kid, 0) + 1

    for kb in kbs:
        docs = docs_by_kb.get(kb.id, [])
        doc_count = len(docs)
        chunk_count = sum(d.chunk_count or 0 for d in docs)
        total_chars = sum(d.file_size or 0 for d in docs)
        total_docs += doc_count
        total_chunks += chunk_count

        # 格式分布
        ext_dist = {}
        for d in docs:
            ext = (d.filename or "").rsplit(".", 1)[-1].lower() if "." in (d.filename or "") else "unknown"
            ext_dist[ext] = ext_dist.get(ext, 0) + 1

        query_count = query_count_by_kb.get(kb.id, 0)

        # 简单健康度评分（0-100）
        health_score = 0
        if doc_count > 0: health_score += 30
        if chunk_count >= 10: health_score += 20
        if chunk_count >= 50: health_score += 10
        if len(ext_dist) >= 2: health_score += 10  # 多格式
        if total_chars and total_chars > 10000: health_score += 15
        if query_count > 0: health_score += 15

        kb_stats.append({
            "id": kb.id,
            "name": kb.name,
            "description": (kb.description or "")[:50],
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "total_chars": total_chars,
            "ext_distribution": ext_dist,
            "query_count_7d": query_count,
            "health_score": min(health_score, 100),
        })

    # 总体统计
    overall = {
        "kb_count": len(kbs),
        "total_docs": total_docs,
        "total_chunks": total_chunks,
        "avg_chunks_per_doc": round(total_chunks / total_docs, 1) if total_docs > 0 else 0,
        "empty_kb_count": sum(1 for k in kb_stats if k["doc_count"] == 0),
        "healthy_kb_count": sum(1 for k in kb_stats if k["health_score"] >= 60),
    }

    return {"knowledge_bases": kb_stats, "overall": overall}
