"""API 路由 — 含 JWT 认证 + 审计日志"""

import json
import shutil
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form, Request, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import create_token, verify_token, verify_password
from app.core.splitter import load_and_split
from app.core.vectorstore import add_documents, query, list_documents, delete_document, delete_kb_documents
from app.core.llm import generate_answer, get_refuse_answer
from app.core.embedding import embed_texts
from app.models.schema import QueryRequest, QueryResponse, UploadResponse, DocumentInfo
from app.models.models import Department, User, KnowledgeBase, AuditLog, Document

router = APIRouter(prefix="/api")

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"

# ─── 不需要认证的路径 ────────────────────────────
PUBLIC_PATHS = {"/api/login"}


# ─── 认证依赖 ────────────────────────────────────

def get_current_user(
    request: Request,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict | None:
    """
    从 Authorization header 解析 JWT。
    公开路径返回 None，保护路径无 token 时抛 401。
    """
    if request.url.path in PUBLIC_PATHS:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录，请先登录")

    token = authorization[7:]
    try:
        payload = verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # 检查用户状态
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="账号已被禁用")

    return payload


# ─── 审计日志工具函数 ────────────────────────────

def log_audit(db: Session, user: dict | None, action: str, resource: str = "",
              detail: str = "", status: str = "success", ip: str = ""):
    """写入审计日志"""
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action,
        resource=resource,
        detail=detail,
        ip_address=ip,
        status=status,
    )
    db.add(log)
    db.commit()


# ─── 权限检查 ────────────────────────────────────
# 角色权限：super_admin=全权 | kb_admin=部门KB管理 | user=部门KB只读

def _get_user_dept_id(db: Session, user_id: str) -> str | None:
    u = db.query(User.department_id).filter(User.id == user_id).first()
    return u[0] if u else None


def get_kb_role(db: Session, user: dict, kb_id: str) -> str | None:
    """获取用户对某知识库的角色"""
    role = user.get("role")
    if role == "super_admin":
        return "admin"
    # 检查该用户的部门是否对该KB有授权
    dept_id = _get_user_dept_id(db, user["sub"])
    if not dept_id:
        return None
    from app.models.models import KBDepartmentAccess
    da = db.query(KBDepartmentAccess).filter(
        KBDepartmentAccess.kb_id == kb_id, KBDepartmentAccess.department_id == dept_id
    ).first()
    if not da:
        return None
    # kb_admin → admin, user → viewer
    return "admin" if role == "kb_admin" else "viewer"


def require_kb_access(db: Session, user: dict, kb_id: str, min_role: str = "viewer"):
    """检查用户对知识库的权限，不足则抛 403"""
    role = get_kb_role(db, user, kb_id)
    levels = {"admin": 3, "editor": 2, "viewer": 1}
    if not role or levels.get(role, 0) < levels.get(min_role, 0):
        raise HTTPException(status_code=403, detail="无权操作此知识库")


def get_accessible_kb_ids(db: Session, user: dict) -> list[str] | None:
    """返回用户可访问的 kb_id 列表，super_admin 返回 None（全部）"""
    if user.get("role") == "super_admin":
        return None
    from app.models.models import KBDepartmentAccess
    dept_id = _get_user_dept_id(db, user["sub"])
    if not dept_id:
        return []
    rows = db.query(KBDepartmentAccess.kb_id).filter(KBDepartmentAccess.department_id == dept_id).all()
    return [r[0] for r in rows]


# ─── 登录 ───────────────────────────────────────

@router.post("/login")
async def login(data: dict, request: Request, db: Session = Depends(get_db)):
    username = data.get("username", "")
    password = data.get("password", "")
    ip = request.client.host if request.client else ""

    user = db.query(User).filter(User.username == username).first()
    if not user or user.status != "active":
        log_audit(db, None, "login", username, "用户不存在或已禁用", "failure", ip)
        raise HTTPException(401, "用户名或密码错误")

    if not verify_password(password, user.password_hash):
        log_audit(db, {"sub": user.id, "username": user.username}, "login", username, "密码错误", "failure", ip)
        raise HTTPException(401, "用户名或密码错误")

    # 更新最后登录时间
    user.last_login = datetime.now(_CST)
    db.commit()

    token = create_token(user.id, user.username, user.role)
    log_audit(db, {"sub": user.id, "username": user.username}, "login", username, "登录成功", "success", ip)

    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        }
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前登录用户信息"""
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(404, "用户不存在")
    return {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name,
        "role": db_user.role,
        "department_id": db_user.department_id,
    }


# ─── 文档相关 ────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    kb_id: str = Form(default="default"),
    chunk_size: int = Form(default=512),
    chunk_overlap: int = Form(default=64),
    chunk_strategy: str = Form(default="semantic"),
    heading_level: int = Form(default=2),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_kb_access(db, user, kb_id, "editor")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        chunks = load_and_split(str(file_path), chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap, strategy=chunk_strategy,
                                heading_level=heading_level)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")
        count = add_documents(chunks, file.filename, kb_id=kb_id)
    except HTTPException:
        raise
    except Exception as e:
        log_audit(db, user, "upload", file.filename, str(e), "failure", request.client.host if request.client else "")
        raise HTTPException(status_code=500, detail=str(e))

    # 写入 Document 表
    import hashlib
    file_hash = hashlib.sha256(open(file_path, 'rb').read()).hexdigest()
    doc = Document(
        filename=file.filename,
        original_name=file.filename,
        file_hash=file_hash,
        file_size=file_path.stat().st_size,
        chunk_count=count,
        kb_id=kb_id,
        uploader_id=user.get("sub"),
        status="indexed",
        chunking_strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    db.add(doc)
    db.commit()

    log_audit(db, user, "upload", file.filename, f"kb={kb_id}, {count}块, 策略={chunk_strategy}", "success",
              request.client.host if request.client else "")
    return UploadResponse(filename=file.filename, chunks=count, message=f"文档已处理，共 {count} 个文本块")


@router.get("/documents")
async def get_documents(kb_id: str = None, page: int = 1, page_size: int = 20, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Document).filter(Document.status != "deleted")
    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
        q = q.filter(Document.kb_id == kb_id)
    else:
        # 无指定KB时，只显示有权限的文档
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            pass  # super_admin 看全部
        elif not accessible_ids:
            return {"total": 0, "items": []}
        else:
            q = q.filter(Document.kb_id.in_(accessible_ids))
    total = q.count()
    docs = q.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = []
    for d in docs:
        size = d.file_size or 0
        if size > 1048576:
            size_str = f"{size/1048576:.1f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.1f} KB"
        else:
            size_str = f"{size} B"
        result.append({"filename": d.filename, "chunks": d.chunk_count, "size": size_str})
    return {"total": total, "items": result}


@router.delete("/documents/{filename:path}")
async def remove_document(
    request: Request,
    filename: str, kb_id: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if kb_id:
        require_kb_access(db, user, kb_id, "editor")
    count = delete_document(filename, kb_id=kb_id)
    if count == 0:
        raise HTTPException(404, "文档不存在")
    # 标记数据库记录为已删除
    q = db.query(Document).filter(Document.filename == filename, Document.status != "deleted")
    if kb_id:
        q = q.filter(Document.kb_id == kb_id)
    for doc in q.all():
        doc.status = "deleted"
    db.commit()
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()
    log_audit(db, user, "delete_doc", filename, f"删除{count}个文本块", "success",
              request.client.host if request.client else "")
    return {"message": f"已删除 {filename}（{count} 个文本块）"}


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(
    request: Request,
    req: QueryRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 权限检查：限定只能搜索有权限的知识库
    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")
        docs = query(req.question, top_k=req.top_k, kb_id=req.kb_id)
    else:
        # 无指定KB时，只搜索有权限的KB
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            docs = query(req.question, top_k=req.top_k)
        elif not accessible_ids:
            docs = []
        else:
            # 搜索所有有权限的KB，合并结果
            all_docs = []
            for kb_id in accessible_ids:
                all_docs.extend(query(req.question, top_k=req.top_k, kb_id=kb_id))
            # 按 distance 排序取 top_k
            all_docs.sort(key=lambda x: x.get("distance", 0))
            docs = all_docs[:req.top_k]
    if not docs:
        log_audit(db, user, "query", req.question[:100], "未命中", "success",
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

    log_audit(db, user, "query", req.question[:100], f"命中{len(docs)}条, 来源={sources}", "success",
              request.client.host if request.client else "")
    return QueryResponse(question=req.question, answer=answer, sources=sources)


# ─── 重建索引 ────────────────────────────────────

@router.post("/reindex")
async def reindex(
    request: Request,
    kb_id: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if kb_id:
        require_kb_access(db, user, kb_id, "editor")
    from app.core.vectorstore import _collection
    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()
    if not results["ids"]:
        return {"message": "没有需要重建的文档", "count": 0}
    docs = results["documents"]
    ids = results["ids"]
    new_embeddings = embed_texts(docs)
    _collection.update(ids=ids, embeddings=new_embeddings)

    log_audit(db, user, "reindex", kb_id or "全部", f"重建{len(ids)}个向量", "success",
              request.client.host if request.client else "")
    return {"message": "索引重建完成", "count": len(ids)}


# ─── 模型配置 ────────────────────────────────────

@router.get("/config/models")
async def get_model_config(user: dict = Depends(get_current_user)):
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"llm": {}, "embedding": {}}


@router.post("/config/models")
async def save_model_config(
    request: Request,
    data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log_audit(db, user, "config_models", "模型配置", "已更新", "success",
              request.client.host if request.client else "")
    return {"message": "配置已保存"}


# ─── 部门 ───────────────────────────────────────

@router.get("/departments")
async def get_departments(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    depts = db.query(Department).filter(Department.status == "active").all()
    return [{"id": d.id, "name": d.name, "path": d.path, "parent_id": d.parent_id} for d in depts]


@router.post("/departments")
async def create_department(
    request: Request,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    dept = Department(
        name=data["name"],
        path=data.get("path", "/" + data["name"]),
        parent_id=data.get("parent_id"),
        description=data.get("description", ""),
    )
    db.add(dept)
    db.commit()
    log_audit(db, user, "create_dept", data["name"], "", "success",
              request.client.host if request.client else "")
    return {"id": dept.id, "name": dept.name}


@router.delete("/departments/{dept_id}")
async def delete_department(
    request: Request,
    dept_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    dept = db.query(Department).get(dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    dept.status = "disabled"
    db.commit()
    log_audit(db, user, "delete_dept", dept.name, "", "success",
              request.client.host if request.client else "")
    return {"message": "已删除"}


# ─── 用户 ───────────────────────────────────────

@router.get("/users")
async def get_users(page: int = 1, page_size: int = 10, role: str = None, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [{
            "id": u.id, "username": u.username, "display_name": u.display_name,
            "email": u.email, "role": u.role, "department_id": u.department_id,
            "department_name": u.department.name if u.department else "",
            "position": u.position, "status": u.status,
            "last_login": str(u.last_login) if u.last_login else None,
        } for u in users]
    }


@router.post("/users")
async def create_user(
    request: Request,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from werkzeug.security import generate_password_hash
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(400, "用户名已存在")
    new_user = User(
        username=data["username"],
        display_name=data["display_name"],
        email=data.get("email", ""),
        password_hash=generate_password_hash(data.get("password", "123456")),
        department_id=data.get("department_id") or None,
        position=data.get("position", ""),
        role=data.get("role", "user"),
        status="active",
    )
    db.add(new_user)
    db.commit()
    log_audit(db, user, "create_user", data["username"], f"role={new_user.role}", "success",
              request.client.host if request.client else "")
    return {"id": new_user.id, "username": new_user.username}


@router.put("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    if "display_name" in data:
        target.display_name = data["display_name"]
    if "email" in data:
        target.email = data["email"]
    if "position" in data:
        target.position = data["position"]
    if "department_id" in data:
        target.department_id = data["department_id"] or None
    if "role" in data:
        target.role = data["role"]
    if "status" in data:
        target.status = data["status"]
    if "password" in data and data["password"]:
        from werkzeug.security import generate_password_hash
        target.password_hash = generate_password_hash(data["password"])
    db.commit()
    log_audit(db, user, "update_user", target.username, json.dumps(data, ensure_ascii=False), "success",
              request.client.host if request.client else "")
    return {"id": target.id, "username": target.username}


@router.delete("/users/{user_id}")
async def delete_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    target.status = "disabled"
    db.commit()
    log_audit(db, user, "delete_user", target.username, "禁用", "success",
              request.client.host if request.client else "")
    return {"message": "已禁用"}


# ─── 知识库 ─────────────────────────────────────

@router.get("/knowledge-bases")
async def get_knowledge_bases(page: int = 1, page_size: int = 10, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    accessible_ids = get_accessible_kb_ids(db, user)
    q = db.query(KnowledgeBase).filter(KnowledgeBase.status != "deleted")
    if accessible_ids is not None:
        if not accessible_ids:
            return {"total": 0, "items": []}
        q = q.filter(KnowledgeBase.id.in_(accessible_ids))
    total = q.count()
    kbs = q.order_by(KnowledgeBase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    from sqlalchemy import func
    rows = db.query(Document.kb_id, func.count(Document.id), func.coalesce(func.sum(Document.chunk_count), 0)).filter(Document.status != "deleted").group_by(Document.kb_id).all()
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
async def create_knowledge_base(
    request: Request,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    kb = KnowledgeBase(
        name=data["name"],
        description=data.get("description", ""),
        embedding_model=data.get("embedding_model", "text-embedding-v3"),
        llm_model=data.get("llm_model", "qwen3.6-plus"),
    )
    db.add(kb)
    db.flush()
    # 自动授权创建者部门为 admin
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if db_user and db_user.department_id:
        from app.models.models import KBDepartmentAccess
        access = KBDepartmentAccess(kb_id=kb.id, department_id=db_user.department_id, role="admin", created_by=user["sub"])
        db.add(access)
    db.commit()
    log_audit(db, user, "create_kb", data["name"], "", "success",
              request.client.host if request.client else "")
    return {"id": kb.id, "name": kb.name}


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    request: Request,
    kb_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    require_kb_access(db, user, kb_id, "admin")
    kb = db.query(KnowledgeBase).get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    if "name" in data:
        kb.name = data["name"]
    if "description" in data:
        kb.description = data["description"]
    if "status" in data:
        kb.status = data["status"]
    if "embedding_model" in data:
        kb.embedding_model = data["embedding_model"]
    if "llm_model" in data:
        kb.llm_model = data["llm_model"]
    db.commit()
    log_audit(db, user, "update_kb", kb.name, json.dumps(data, ensure_ascii=False), "success",
              request.client.host if request.client else "")
    return {"id": kb.id, "name": kb.name}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    request: Request,
    kb_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    require_kb_access(db, user, kb_id, "admin")
    kb = db.query(KnowledgeBase).get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    kb.status = "deleted"
    # 标记该KB下所有文档为已删除
    db.query(Document).filter(Document.kb_id == kb_id, Document.status != "deleted").update({"status": "deleted"})
    db.commit()
    delete_kb_documents(kb_id)
    log_audit(db, user, "delete_kb", kb.name, "", "success",
              request.client.host if request.client else "")
    return {"message": "已删除"}


# ─── 分块查看/编辑 ───────────────────────────────

@router.get("/documents/{filename}/chunks")
async def get_document_chunks(filename: str, kb_id: str = None, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取文档的所有分块"""
    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
    from app.core.vectorstore import _collection
    if kb_id:
        results = _collection.get(where={"$and": [{"source": filename}, {"kb_id": kb_id}]})
    else:
        results = _collection.get(where={"source": filename})
    chunks = []
    for i in range(len(results["ids"])):
        meta = results["metadatas"][i] if results["metadatas"] else {}
        chunks.append({
            "id": results["ids"][i],
            "index": i + 1,
            "text": results["documents"][i],
            "char_count": len(results["documents"][i]),
            "source": meta.get("source", filename),
            "kb_id": meta.get("kb_id", ""),
        })
    return {"filename": filename, "total": len(chunks), "chunks": chunks}


@router.put("/chunks/{chunk_id}")
async def update_chunk(chunk_id: str, data: dict, user: dict = Depends(get_current_user)):
    from app.core.vectorstore import _collection, embed_texts
    new_text = data.get("text", "").strip()
    if not new_text:
        raise HTTPException(400, "分块内容不能为空")
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        raise HTTPException(404, "分块不存在")
    new_embedding = embed_texts([new_text])[0]
    _collection.update(ids=[chunk_id], documents=[new_text], embeddings=[new_embedding])
    return {"message": "分块已更新", "id": chunk_id, "char_count": len(new_text)}


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str, user: dict = Depends(get_current_user)):
    from app.core.vectorstore import _collection
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        raise HTTPException(404, "分块不存在")
    _collection.delete(ids=[chunk_id])
    return {"message": "分块已删除"}


# ─── Prompt 管理 ─────────────────────────────────

PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "prompts.json"


@router.get("/config/prompts")
async def get_prompts(user: dict = Depends(get_current_user)):
    if PROMPTS_PATH.exists():
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@router.post("/config/prompts")
async def save_prompts(data: dict, user: dict = Depends(get_current_user)):
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"message": "Prompt 已保存"}


# ─── 知识库授权 ────────────────────────────────

@router.get("/kb-access")
async def get_kb_access(kb_id: str = None, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBDepartmentAccess, KBUserAccess
    q = db.query(KBDepartmentAccess)
    if kb_id:
        q = q.filter(KBDepartmentAccess.kb_id == kb_id)
    records = q.all()
    return [{"id": r.id, "kb_id": r.kb_id, "department_id": r.department_id, "role": r.role} for r in records]


@router.post("/kb-access")
async def set_kb_access(data: dict, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBDepartmentAccess
    kb_id = data["kb_id"]
    dept_id = data["department_id"]
    role = data["role"]
    existing = db.query(KBDepartmentAccess).filter(
        KBDepartmentAccess.kb_id == kb_id,
        KBDepartmentAccess.department_id == dept_id
    ).first()
    if existing:
        existing.role = role
    else:
        record = KBDepartmentAccess(kb_id=kb_id, department_id=dept_id, role=role, created_by=user["sub"])
        db.add(record)
    db.commit()
    return {"message": "已更新"}


@router.delete("/kb-access")
async def remove_kb_access(kb_id: str, department_id: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBDepartmentAccess
    record = db.query(KBDepartmentAccess).filter(
        KBDepartmentAccess.kb_id == kb_id,
        KBDepartmentAccess.department_id == department_id
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return {"message": "已删除"}


# ─── 知识库用户授权 ─────────────────────────────

@router.get("/kb-user-access")
async def get_kb_user_access(kb_id: str = None, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBUserAccess
    q = db.query(KBUserAccess)
    if kb_id:
        q = q.filter(KBUserAccess.kb_id == kb_id)
    records = q.all()
    result = []
    for r in records:
        u = db.query(User).filter(User.id == r.user_id).first()
        result.append({
            "id": r.id, "kb_id": r.kb_id, "user_id": r.user_id,
            "username": u.username if u else r.user_id,
            "display_name": u.display_name if u else "",
            "department_name": u.department.name if u and u.department else "",
            "role": r.role,
        })
    return result


@router.post("/kb-user-access")
async def set_kb_user_access(data: dict, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBUserAccess
    kb_id = data["kb_id"]
    user_id = data["user_id"]
    role = data["role"]
    existing = db.query(KBUserAccess).filter(
        KBUserAccess.kb_id == kb_id,
        KBUserAccess.user_id == user_id
    ).first()
    if existing:
        existing.role = role
    else:
        record = KBUserAccess(kb_id=kb_id, user_id=user_id, role=role, created_by=user["sub"])
        db.add(record)
    db.commit()
    return {"message": "已更新"}


@router.delete("/kb-user-access")
async def remove_kb_user_access(kb_id: str, user_id: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.models.models import KBUserAccess
    record = db.query(KBUserAccess).filter(
        KBUserAccess.kb_id == kb_id,
        KBUserAccess.user_id == user_id
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return {"message": "已删除"}


# ─── 审计日志查询 ────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    action: str = None,
    username: str = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """查询审计日志"""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if username:
        q = q.filter(AuditLog.username == username)
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [{
        "id": l.id, "username": l.username, "action": l.action,
        "resource": l.resource, "detail": l.detail,
        "ip_address": l.ip_address, "status": l.status,
        "created_at": str(l.created_at),
    } for l in logs]}
