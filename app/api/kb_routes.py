"""知识库 CRUD API"""

import json
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.models import KnowledgeBase, Document, User
from app.api.deps import get_current_user, log_audit, require_kb_access, get_accessible_kb_ids

router = APIRouter(prefix="/api", tags=["知识库"])



@router.get("/knowledge-bases")
async def get_knowledge_bases(page: int = 1, page_size: int = 10,
                               db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    accessible_ids = get_accessible_kb_ids(db, user)
    q = db.query(KnowledgeBase).filter(KnowledgeBase.status != "deleted")
    if accessible_ids is not None:
        if not accessible_ids:
            return {"total": 0, "items": []}
        q = q.filter(KnowledgeBase.id.in_(accessible_ids))
    total = q.count()
    kbs = q.order_by(KnowledgeBase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    rows = db.query(Document.kb_id, func.count(Document.id),
                    func.coalesce(func.sum(Document.chunk_count), 0)
                    ).filter(Document.status != "deleted").group_by(Document.kb_id).all()
    doc_stats = {r[0]: {"doc_count": r[1], "chunk_count": r[2]} for r in rows}

    items = []
    for k in kbs:
        stats = doc_stats.get(k.id, {"doc_count": 0, "chunk_count": 0})
        items.append({
            "id": k.id, "name": k.name, "description": k.description,
            "embedding_model": k.embedding_model, "llm_model": k.llm_model,
            "status": k.status, "created_at": str(k.created_at),
            "doc_count": stats["doc_count"], "chunk_count": stats["chunk_count"],
        })
    return {"total": total, "items": items}


@router.post("/knowledge-bases")
async def create_knowledge_base(data: dict, request: Request,
                                 db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    kb = KnowledgeBase(
        name=data["name"], description=data.get("description", ""),
        embedding_model=data.get("embedding_model", "text-embedding-v3"),
        llm_model=data.get("llm_model", "qwen3.6-plus"),
    )
    db.add(kb)
    db.flush()
    # 自动授权创建者部门
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if db_user and db_user.department_id:
        from app.models.models import KBDepartmentAccess
        access = KBDepartmentAccess(kb_id=kb.id, department_id=db_user.department_id,
                                    role="admin", created_by=user["sub"])
        db.add(access)
    db.commit()
    log_audit(db, user, "create_kb", data["name"], "", "success",
               request.client.host if request.client else "")
    return {"id": kb.id, "name": kb.name}


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(kb_id: str, data: dict, request: Request,
                                 db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    require_kb_access(db, user, kb_id, "admin")
    kb = db.query(KnowledgeBase).get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    for field in ("name", "description", "status", "embedding_model", "llm_model"):
        if field in data:
            setattr(kb, field, data[field])
    db.commit()
    log_audit(db, user, "update_kb", kb.name, json.dumps(data, ensure_ascii=False), "success",
               request.client.host if request.client else "")
    return {"id": kb.id, "name": kb.name}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str, request: Request,
                                 db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    require_kb_access(db, user, kb_id, "admin")
    kb = db.query(KnowledgeBase).get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    kb.status = "deleted"
    db.query(Document).filter(Document.kb_id == kb_id, Document.status != "deleted").update({"status": "deleted"})
    db.commit()
    from app.core.vectorstore import delete_kb_documents
    delete_kb_documents(kb_id)
    log_audit(db, user, "delete_kb", kb.name, "", "success",
               request.client.host if request.client else "")
    return {"message": "已删除"}
