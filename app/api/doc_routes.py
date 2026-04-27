"""文档上传/查询/分块 API"""

import hashlib
import shutil
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

_CST = timezone(timedelta(hours=8))

from fastapi import APIRouter, HTTPException, Depends, Request, File, UploadFile, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Document
from app.api.deps import get_current_user, log_audit, require_kb_access, get_accessible_kb_ids

router = APIRouter(prefix="/api", tags=["文档"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


def _process_pdf_background(
    task_id: str,
    file_path: str,
    filename: str,
    kb_id: str,
    file_hash: str,
    uploader_id: str,
    file_size: int,
    chunk_size: int,
    chunk_overlap: int,
    chunk_strategy: str,
    heading_level: int,
):
    """后台线程：处理 PDF 文档（OCR + 分块 + 向量化）"""
    from app.core import progress
    try:
        from app.core.splitter import load_and_split
        from app.core.vectorstore import add_documents

        def on_page(current, total):
            pct = int(current / total * 100)
            progress.update(task_id,
                stage="processing",
                current_page=current,
                total_pages=total,
                percent=pct,
                message=f"OCR 处理中: 第 {current}/{total} 页 ({pct}%)",
            )

        progress.update(task_id, stage="processing", message="OCR 处理中...")

        # load_and_split 需要支持 progress_callback
        chunks, warnings = load_and_split(
            str(file_path),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strategy=chunk_strategy,
            heading_level=heading_level,
            progress_callback=on_page,
        )

        if not chunks:
            progress.finish(task_id, error="文档内容为空或无法解析")
            return

        progress.update(task_id, stage="indexing", percent=95, message="写入向量库...")
        count = add_documents(chunks, filename, kb_id=kb_id)

        # 写入 DB
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            doc = Document(
                filename=filename, original_name=filename,
                file_hash=file_hash, file_size=file_size,
                chunk_count=count, kb_id=kb_id,
                uploader_id=uploader_id, status="indexed",
                chunking_strategy=chunk_strategy, chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            db.add(doc)
            db.commit()
        finally:
            db.close()

        resp = {"filename": filename, "chunks": count,
                "message": f"文档已处理，共 {count} 个文本块"}
        if warnings:
            resp["warnings"] = warnings
        progress.finish(task_id, result=resp)

    except ValueError as e:
        progress.finish(task_id, error=str(e))
    except Exception as e:
        progress.finish(task_id, error=str(e))



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

    # 文件格式校验
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt", ".xlsx", ".xls", ".csv", ".pptx"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {file_ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename

    # 先读取内容算 hash
    content = await file.read()

    # 文件大小校验（50MB）
    MAX_FILE_SIZE = 50 * 1024 * 1024
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件过大: {len(content)/1024/1024:.1f}MB，最大允许 50MB")

    file_hash = hashlib.sha256(content).hexdigest()

    # 清理同 KB 内同名的已删除记录（物理删除，释放唯一约束）
    from app.core.vectorstore import delete_document
    deleted_same = db.query(Document).filter(
        Document.kb_id == kb_id, Document.filename == file.filename,
        Document.status == "deleted"
    ).all()
    for d in deleted_same:
        db.delete(d)
    if deleted_same:
        db.commit()

    # 检查同 KB 内同名文件 → 版本替换
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

    # PDF 文件：异步处理，返回 task_id
    if file_ext == ".pdf":
        from app.core.progress import create_task
        from app.core.ocr import OCREngine

        task_id = uuid.uuid4().hex[:16]
        try:
            engine = OCREngine(device="cpu")
            total_pages = engine.pdf_page_count(str(file_path))
        except Exception:
            total_pages = 0

        create_task(task_id, total_pages=total_pages)

        # 后台线程处理
        t = threading.Thread(
            target=_process_pdf_background,
            args=(task_id, file_path, file.filename, kb_id,
                  file_hash, user.get("sub"), file_path.stat().st_size,
                  chunk_size, chunk_overlap, chunk_strategy, heading_level),
            daemon=True,
        )
        t.start()

        return {"task_id": task_id, "total_pages": total_pages,
                "filename": file.filename,
                "message": f"文件已上传，共 {total_pages} 页，正在 OCR 处理..."}

    # 非 PDF 文件：同步处理
    try:
        from app.core.splitter import load_and_split
        from app.core.vectorstore import add_documents
        chunks, warnings = load_and_split(str(file_path), chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap, strategy=chunk_strategy,
                                heading_level=heading_level)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")
        count = add_documents(chunks, file.filename, kb_id=kb_id)
    except HTTPException:
        raise
    except ValueError as e:
        log_audit(db, user, "upload", file.filename, str(e), "failure",
                   request.client.host if request.client else "")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_audit(db, user, "upload", file.filename, str(e), "failure",
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

    log_audit(db, user, "upload", file.filename,
               f"kb={kb_id}, {count}块, 策略={chunk_strategy}", "success",
               request.client.host if request.client else "")
    resp = {"filename": file.filename, "chunks": count,
            "message": f"文档已处理，共 {count} 个文本块"}
    if warnings:
        resp["warnings"] = warnings
    return resp


@router.get("/upload/progress/{task_id}")
async def get_upload_progress(task_id: str):
    """查询上传任务进度"""
    from app.core.progress import get, cleanup
    task = get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["done"] and task.get("result"):
        cleanup(task_id)
    return task


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

    # 物理删除文档记录
    q = db.query(Document).filter(Document.filename == filename)
    if kb_id:
        q = q.filter(Document.kb_id == kb_id)
    deleted_count = q.delete()
    db.commit()

    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()

    log_audit(db, user, "delete_doc", filename, f"删除{count}个文本块", "success",
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
