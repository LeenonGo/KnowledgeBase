"""问答 & 重建索引 API — 含缓存"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.cache import query_cache
from app.models.schema import QueryRequest, QueryResponse
from app.models.models import AuditLog
from app.api.deps import get_current_user, require_kb_access, get_accessible_kb_ids

router = APIRouter(prefix="/api", tags=["问答"])


def _log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(
    request: Request, req: QueryRequest,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    from app.core.vectorstore import query as vector_query
    from app.core.llm import generate_answer, get_refuse_answer

    # 查缓存
    cache_key_kb = req.kb_id or "all"
    cached = query_cache.get(req.question, cache_key_kb)
    if cached:
        _log_audit(db, user, "query", req.question[:100], "缓存命中", "success",
                   request.client.host if request.client else "")
        return QueryResponse(**cached)

    # 检索
    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")
        docs = vector_query(req.question, top_k=req.top_k, kb_id=req.kb_id,
                            use_hybrid=req.use_hybrid, use_reranker=req.use_reranker)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            docs = vector_query(req.question, top_k=req.top_k,
                                use_hybrid=req.use_hybrid, use_reranker=req.use_reranker)
        elif not accessible_ids:
            docs = []
        else:
            all_docs = []
            for kb_id in accessible_ids:
                all_docs.extend(vector_query(req.question, top_k=req.top_k, kb_id=kb_id,
                                             use_hybrid=req.use_hybrid, use_reranker=req.use_reranker))
            all_docs.sort(key=lambda x: x.get("distance", 0))
            docs = all_docs[:req.top_k]

    if not docs:
        _log_audit(db, user, "query", req.question[:100], "未命中", "success",
                   request.client.host if request.client else "")
        refuse = get_refuse_answer()
        result = {"question": req.question, "answer": refuse, "sources": []}
        query_cache.set(req.question, result, cache_key_kb, ttl=300)  # 拒答缓存 5 分钟
        return QueryResponse(**result)

    # 拼上下文
    MAX_CONTEXT_CHARS = 3000
    context_parts = []
    total_chars = 0
    for d in docs:
        part = f'[来源: {d["source"]}]\n{d["text"]}'
        if total_chars + len(part) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total_chars
            if remaining > 100:
                context_parts.append(part[:remaining] + "...")
            break
        context_parts.append(part)
        total_chars += len(part)

    context = "\n\n".join(context_parts)
    sources = list(set(d["source"] for d in docs))
    answer = generate_answer(req.question, context)

    result = {"question": req.question, "answer": answer, "sources": sources}
    query_cache.set(req.question, result, cache_key_kb, ttl=3600)  # 正常结果缓存 1 小时

    _log_audit(db, user, "query", req.question[:100],
               f"命中{len(docs)}条, 来源={sources}", "success",
               request.client.host if request.client else "")
    return QueryResponse(**result)


@router.get("/cache/stats")
async def get_cache_stats(user: dict = Depends(get_current_user)):
    """查询缓存统计"""
    return query_cache.stats()


@router.post("/cache/clear")
async def clear_cache(user: dict = Depends(get_current_user)):
    """清空查询缓存"""
    query_cache.clear()
    return {"message": "缓存已清空"}


@router.post("/reindex")
async def reindex(
    request: Request, kb_id: str = None,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    from app.core.vectorstore import reindex_kb

    if kb_id:
        require_kb_access(db, user, kb_id, "editor")

    count = reindex_kb(kb_id)
    if count == 0:
        return {"message": "没有需要重建的文档", "count": 0}

    # 重建索引后清空缓存
    query_cache.clear()

    _log_audit(db, user, "reindex", kb_id or "全部", f"重建{count}个向量", "success",
               request.client.host if request.client else "")
    return {"message": "索引重建完成", "count": count}
