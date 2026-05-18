"""数据源同步引擎 — 调度 / Diff / 执行"""

import json
import asyncio
import threading
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.ds_models import DataSource, SyncStatus
from app.models.models import Document

logger = logging.getLogger(__name__)
_CST = timezone(timedelta(hours=8))

# 正在执行的同步任务（防重复）
_sync_locks: dict[str, threading.Lock] = {}


def _get_lock(source_id: str) -> threading.Lock:
    if source_id not in _sync_locks:
        _sync_locks[source_id] = threading.Lock()
    return _sync_locks[source_id]


def sync_data_source(source_id: str, db: Session) -> dict:
    """同步单个数据源（同步执行，供后台线程调用）"""
    lock = _get_lock(source_id)
    if not lock.acquire(blocking=False):
        logger.warning(f"[Sync] 数据源 {source_id} 正在同步中，跳过")
        return {"status": "skipped", "message": "正在同步中"}

    try:
        return _do_sync(source_id, db)
    finally:
        lock.release()


def _do_sync(source_id: str, db: Session) -> dict:
    """执行同步"""
    from app.core.ds_adapters import get_adapter

    # 1. 加载数据源
    ds = db.query(DataSource).get(source_id)
    if not ds:
        return {"status": "error", "message": "数据源不存在"}

    config = json.loads(ds.config) if ds.config else {}
    config["source_id"] = source_id

    # 2. 更新状态为 syncing
    ds.sync_status = SyncStatus.SYNCING
    db.commit()

    result = {
        "status": "success",
        "started_at": datetime.now(_CST).isoformat(),
        "total_remote": 0,
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "errors": 0,
        "error_details": [],
    }

    try:
        # 3. 获取适配器
        adapter = get_adapter(ds.source_type)

        # 4. 获取远程文件列表
        remote_files = adapter.list_files(config)
        result["total_remote"] = len(remote_files)
        remote_map = {f["path"]: f for f in remote_files}

        # 5. 获取本地已有文档（通过 filename 前缀识别来源）
        source_prefix = f"[source:{source_id}]"
        local_docs = db.query(Document).filter(
            Document.kb_id == ds.kb_id,
            Document.filename.like(f"{source_prefix}%"),
            Document.status != "deleted",
        ).all()
        local_map = {}
        for doc in local_docs:
            # 去掉前缀还原原始路径
            orig_path = doc.filename[len(source_prefix):]
            local_map[orig_path] = doc

        # 6. Diff 对比
        from app.core.splitter import load_and_split
        from app.core.vectorstore import add_documents, delete_document
        from app.api.doc_routes import UPLOAD_DIR

        # 新增 + 修改
        for rel_path, file_info in remote_map.items():
            try:
                prefixed_name = f"{source_prefix}{rel_path}"
                local_doc = local_map.get(rel_path)

                if local_doc:
                    if local_doc.file_hash == file_info["hash"]:
                        result["skipped"] += 1
                        continue
                    # hash 不同 → 更新
                    delete_document(local_doc.filename, kb_id=ds.kb_id)
                    local_doc.status = "deleted"
                    local_doc.deleted_at = datetime.now(_CST)
                    is_update = True
                else:
                    is_update = False

                # 下载文件
                local_path = adapter.download_file(config, file_info, source_id=source_id)

                # 处理文件（分块+向量化）
                chunks, warnings = load_and_split(
                    local_path, chunk_size=512, chunk_overlap=64, strategy="fixed"
                )
                if not chunks:
                    logger.warning(f"[Sync] 文件内容为空: {rel_path}")
                    continue

                count = add_documents(chunks, prefixed_name, kb_id=ds.kb_id)

                # 创建 Document 记录
                import hashlib
                file_size = Path(local_path).stat().st_size if Path(local_path).exists() else 0
                doc = Document(
                    filename=prefixed_name,
                    original_name=Path(rel_path).name,
                    file_hash=file_info["hash"],
                    file_size=file_size,
                    chunk_count=count,
                    kb_id=ds.kb_id,
                    uploader_id=None,
                    status="indexed",
                    chunking_strategy="fixed",
                    chunk_size=512,
                    chunk_overlap=64,
                )
                db.add(doc)

                if is_update:
                    result["updated"] += 1
                else:
                    result["added"] += 1

            except Exception as e:
                result["errors"] += 1
                result["error_details"].append(f"{rel_path}: {str(e)[:100]}")
                logger.error(f"[Sync] 文件处理失败 {rel_path}: {e}")
                # 连续失败过多（如 API 额度耗尽），快速中止
                if result["errors"] >= 10 and result["added"] == 0 and result["updated"] == 0:
                    result["status"] = "error"
                    result["error"] = f"连续 {result['errors']} 个文件处理失败，已中止同步。请检查 API 额度或配置。"
                    logger.error(f"[Sync] 连续失败过多，中止同步")
                    break

        # 删除（远程没有但本地有的）
        for rel_path, local_doc in local_map.items():
            if rel_path not in remote_map:
                delete_document(local_doc.filename, kb_id=ds.kb_id)
                local_doc.status = "deleted"
                local_doc.deleted_at = datetime.now(_CST)
                result["deleted"] += 1

        db.commit()

        # 清理适配器临时文件
        try:
            adapter.cleanup(source_id)
        except Exception:
            pass

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:500]
        logger.error(f"[Sync] 同步失败: {e}")

    # 7. 更新数据源状态
    result["finished_at"] = datetime.now(_CST).isoformat()
    ds.sync_status = SyncStatus.SUCCESS if result["status"] == "success" else SyncStatus.ERROR
    ds.last_sync_at = datetime.now(_CST)
    ds.last_sync_result = json.dumps(result, ensure_ascii=False)
    db.commit()

    logger.info(f"[Sync] 数据源 {ds.name} 同步完成: +{result['added']} ~{result['updated']} -{result['deleted']} err={result['errors']}")
    return result


def run_sync_background(source_id: str, db_session_factory):
    """后台线程执行同步"""
    db = db_session_factory()
    try:
        sync_data_source(source_id, db)
    finally:
        db.close()
