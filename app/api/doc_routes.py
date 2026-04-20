"""文档上传/查询/分块 API"""

import hashlib
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

_CST = timezone(timedelta(hours=8))

from fastapi import APIRouter, HTTPException, Depends, Request, File, UploadFile, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Document, AuditLog
from app.api.deps import get_current_user, require_kb_access, get_accessible_kb_ids

router = APIRouter(prefix="/api", tags=["文档"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


def _log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


@router.post("/upload")
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

    # 先读取内容算 hash
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # 检查同 KB 内同名文件 → 版本替换
    from app.core.vectorstore import delete_document
    same_name = db.query(Document).filter(
        Document.kb_id == kb_id, Document.filename == file.filename,
        Document.status != "deleted"
    ).first()
    if same_name:
        if same_name.file_hash == file_hash:
            raise HTTPException(400, "文件内容完全相同，无需重复上传")
        # 内容不同 → 替换旧版本
        delete_document(file.filename, kb_id=kb_id)
        same_name.status = "deleted"
        same_name.deleted_at = datetime.now(_CST)
        db.commit()

    # 检查同 KB 内是否有完全相同内容的其他文件
    same_hash = db.query(Document).filter(
        Document.kb_id == kb_id, Document.file_hash == file_hash,
        Document.status != "deleted", Document.filename != file.filename,
    ).first()
    if same_hash:
        raise HTTPException(400, f"内容相同的文件已存在: {same_hash.filename}")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        from app.core.splitter import load_and_split
        from app.core.vectorstore import add_documents
        chunks = load_and_split(str(file_path), chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap, strategy=chunk_strategy,
                                heading_level=heading_level)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")
        count = add_documents(chunks, file.filename, kb_id=kb_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_audit(db, user, "upload", file.filename, str(e), "failure",
                   request.client.host if request.client else "")
        raise HTTPException(status_code=500, detail=str(e))

    doc = Document(
        filename=file.filename, original_name=file.filename,
        file_hash=file_hash, file_size=file_path.stat().st_size,
        chunk_count=count, kb_id=kb_id,
        uploader_id=user.get("sub"), status="indexed",
        chunking_strategy=chunk_strategy, chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    db.add(doc)
    db.commit()

    _log_audit(db, user, "upload", file.filename,
               f"kb={kb_id}, {count}块, 策略={chunk_strategy}", "success",
               request.client.host if request.client else "")
    return {"filename": file.filename, "chunks": count,
            "message": f"文档已处理，共 {count} 个文本块"}


@router.get("/documents")
async def get_documents(kb_id: str = None, page: int = 1, page_size: int = 20,
                        user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Document).filter(Document.status != "deleted")
    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
        q = q.filter(Document.kb_id == kb_id)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            pass
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
    request: Request, filename: str, kb_id: str = None,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    if kb_id:
        require_kb_access(db, user, kb_id, "editor")

    from app.core.vectorstore import delete_document
    count = delete_document(filename, kb_id=kb_id)
    if count == 0:
        raise HTTPException(404, "文档不存在")

    q = db.query(Document).filter(Document.filename == filename, Document.status != "deleted")
    if kb_id:
        q = q.filter(Document.kb_id == kb_id)
    for doc in q.all():
        doc.status = "deleted"
    db.commit()

    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()

    _log_audit(db, user, "delete_doc", filename, f"删除{count}个文本块", "success",
               request.client.host if request.client else "")
    return {"message": f"已删除 {filename}（{count} 个文本块）"}


@router.get("/documents/{filename}/chunks")
async def get_document_chunks(filename: str, kb_id: str = None,
                              user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
    from app.core.vectorstore import get_chunks
    chunks = get_chunks(filename, kb_id=kb_id)
    return {"filename": filename, "total": len(chunks), "chunks": chunks}


@router.put("/chunks/{chunk_id}")
async def update_chunk(chunk_id: str, data: dict, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(403, "无权编辑分块")
    from app.core.vectorstore import update_chunk as vs_update
    new_text = data.get("text", "").strip()
    if not new_text:
        raise HTTPException(400, "分块内容不能为空")
    try:
        result = vs_update(chunk_id, new_text)
        return {"message": "分块已更新", **result}
    except ValueError:
        raise HTTPException(404, "分块不存在")


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(403, "无权删除分块")
    from app.core.vectorstore import delete_chunk as vs_delete
    if not vs_delete(chunk_id):
        raise HTTPException(404, "分块不存在")
    return {"message": "分块已删除"}
