"""API 路由"""

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.splitter import load_and_split
from app.core.vectorstore import add_documents, query, list_documents, delete_document, delete_kb_documents
from app.core.llm import generate_answer
from app.core.embedding import embed_texts
from app.models.schema import QueryRequest, QueryResponse, UploadResponse, DocumentInfo
from app.models.models import Department, User, KnowledgeBase

router = APIRouter(prefix="/api")

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"


# ─── 文档相关 ────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    kb_id: str = Form(default="default"),
    chunk_size: int = Form(default=512),
    chunk_overlap: int = Form(default=64),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        chunks = load_and_split(str(file_path), chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")
        count = add_documents(chunks, file.filename, kb_id=kb_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return UploadResponse(filename=file.filename, chunks=count, message=f"文档已处理，共 {count} 个文本块")


@router.get("/documents", response_model=list[DocumentInfo])
async def get_documents(kb_id: str = None):
    return list_documents(kb_id=kb_id)


@router.delete("/documents/{filename:path}")
async def remove_document(filename: str, kb_id: str = None):
    count = delete_document(filename, kb_id=kb_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="文档不存在")
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()
    return {"message": f"已删除 {filename}（{count} 个文本块）"}


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(req: QueryRequest):
    docs = query(req.question, top_k=req.top_k, kb_id=req.kb_id)
    if not docs:
        return QueryResponse(question=req.question, answer="知识库中暂无相关内容，请先上传文档。", sources=[])
    context = "\n\n".join(f"[来源: {d['source']}]\n{d['text']}" for d in docs)
    sources = list(set(d["source"] for d in docs))
    answer = generate_answer(req.question, context)
    return QueryResponse(question=req.question, answer=answer, sources=sources)


# ─── 重建索引 ────────────────────────────────────

@router.post("/reindex")
async def reindex(kb_id: str = None):
    """重新向量化指定知识库的所有文档（或全部文档）"""
    import chromadb
    from app.core.vectorstore import _collection, embed_texts

    # 获取需要重建的文档
    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()

    if not results["ids"]:
        return {"message": "没有需要重建的文档", "count": 0}

    docs = results["documents"]
    ids = results["ids"]
    metadatas = results["metadatas"]

    # 用新的 Embedding 模型重新向量化
    new_embeddings = embed_texts(docs)

    # 更新向量
    _collection.update(
        ids=ids,
        embeddings=new_embeddings,
    )

    return {"message": f"索引重建完成", "count": len(ids)}


# ─── 模型配置 ────────────────────────────────────

@router.get("/config/models")
async def get_model_config():
    """获取当前模型配置"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"llm": {}, "embedding": {}}


@router.post("/config/models")
async def save_model_config(data: dict):
    """保存模型配置"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"message": "配置已保存"}


# ─── 部门 ───────────────────────────────────────

@router.get("/departments")
async def get_departments(db: Session = Depends(get_db)):
    depts = db.query(Department).filter(Department.status == "active").all()
    return [{"id": d.id, "name": d.name, "path": d.path, "parent_id": d.parent_id} for d in depts]


@router.post("/departments")
async def create_department(data: dict, db: Session = Depends(get_db)):
    dept = Department(
        name=data["name"],
        path=data.get("path", "/" + data["name"]),
        parent_id=data.get("parent_id"),
        description=data.get("description", ""),
    )
    db.add(dept)
    db.commit()
    return {"id": dept.id, "name": dept.name}


@router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, db: Session = Depends(get_db)):
    dept = db.query(Department).get(dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    dept.status = "disabled"
    db.commit()
    return {"message": "已删除"}


# ─── 用户 ───────────────────────────────────────

@router.get("/users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.status == "active").all()
    return [{
        "id": u.id, "username": u.username, "display_name": u.display_name,
        "email": u.email, "role": u.role, "department_id": u.department_id,
        "department_name": u.department.name if u.department else "",
        "position": u.position, "status": u.status,
    } for u in users]


@router.post("/users")
async def create_user(data: dict, db: Session = Depends(get_db)):
    from werkzeug.security import generate_password_hash
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(400, "用户名已存在")
    user = User(
        username=data["username"],
        display_name=data["display_name"],
        email=data.get("email", ""),
        password_hash=generate_password_hash(data.get("password", "123456")),
        department_id=data.get("department_id"),
        role=data.get("role", "user"),
        status="active",
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "username": user.username}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    user.status = "disabled"
    db.commit()
    return {"message": "已删除"}


# ─── 知识库 ─────────────────────────────────────

@router.get("/knowledge-bases")
async def get_knowledge_bases(db: Session = Depends(get_db)):
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.status != "deleted").all()
    return [{
        "id": k.id, "name": k.name, "description": k.description,
        "embedding_model": k.embedding_model, "llm_model": k.llm_model,
        "status": k.status, "created_at": str(k.created_at),
    } for k in kbs]


@router.post("/knowledge-bases")
async def create_knowledge_base(data: dict, db: Session = Depends(get_db)):
    kb = KnowledgeBase(
        name=data["name"],
        description=data.get("description", ""),
        embedding_model=data.get("embedding_model", "text-embedding-v3"),
        llm_model=data.get("llm_model", "qwen3.6-plus"),
    )
    db.add(kb)
    db.commit()
    return {"id": kb.id, "name": kb.name}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: str, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).get(kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    kb.status = "deleted"
    db.commit()
    delete_kb_documents(kb_id)
    return {"message": "已删除"}


# ─── 分块查看/编辑 ───────────────────────────────

@router.get("/documents/{filename}/chunks")
async def get_document_chunks(filename: str, kb_id: str = None):
    """获取文档的所有分块"""
    import chromadb
    from app.core.vectorstore import _client, _collection

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
async def update_chunk(chunk_id: str, data: dict):
    """编辑单个分块内容"""
    from app.core.vectorstore import _collection, embed_texts

    new_text = data.get("text", "").strip()
    if not new_text:
        raise HTTPException(400, "分块内容不能为空")

    # 获取旧数据
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        raise HTTPException(404, "分块不存在")

    # 重新向量化
    new_embedding = embed_texts([new_text])[0]

    _collection.update(
        ids=[chunk_id],
        documents=[new_text],
        embeddings=[new_embedding],
    )

    return {"message": "分块已更新", "id": chunk_id, "char_count": len(new_text)}


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str):
    """删除单个分块"""
    from app.core.vectorstore import _collection

    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        raise HTTPException(404, "分块不存在")

    _collection.delete(ids=[chunk_id])
    return {"message": "分块已删除"}
