"""问答 & 重建索引 API"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
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

    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")
        docs = vector_query(req.question, top_k=req.top_k, kb_id=req.kb_id)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            docs = vector_query(req.question, top_k=req.top_k)
        elif not accessible_ids:
            docs = []
        else:
            all_docs = []
            for kb_id in accessible_ids:
                all_docs.extend(vector_query(req.question, top_k=req.top_k, kb_id=kb_id))
            all_docs.sort(key=lambda x: x.get("distance", 0))
            docs = all_docs[:req.top_k]

    if not docs:
        _log_audit(db, user, "query", req.question[:100], "未命中", "success",
                   request.client.host if request.client else "")
        return QueryResponse(question=req.question, answer=get_refuse_answer(), sources=[])

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

    _log_audit(db, user, "query", req.question[:100],
               f"命中{len(docs)}条, 来源={sources}", "success",
               request.client.host if request.client else "")
    return QueryResponse(question=req.question, answer=answer, sources=sources)


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

    _log_audit(db, user, "reindex", kb_id or "全部", f"重建{count}个向量", "success",
               request.client.host if request.client else "")
    return {"message": "索引重建完成", "count": count}
