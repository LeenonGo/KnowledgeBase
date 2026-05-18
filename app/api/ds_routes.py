"""数据源同步 API 路由"""

import json
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.api.deps import get_current_user, require_kb_access, log_audit
from app.models.ds_models import DataSource, SyncStatus

router = APIRouter(prefix="/api/data-sources", tags=["数据源同步"])


@router.get("")
async def list_data_sources(
    kb_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取数据源列表"""
    q = db.query(DataSource)
    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
        q = q.filter(DataSource.kb_id == kb_id)
    sources = q.order_by(DataSource.created_at.desc()).all()
    return [s.to_dict() for s in sources]


@router.post("")
async def create_data_source(
    data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新增数据源"""
    kb_id = data.get("kb_id", "")
    if not kb_id:
        raise HTTPException(400, "kb_id 不能为空")
    require_kb_access(db, user, kb_id, "editor")

    name = data.get("name", "").strip()
    source_type = data.get("source_type", "").strip()
    config = data.get("config", {})
    sync_cron = data.get("sync_cron", "").strip()

    if not name:
        raise HTTPException(400, "名称不能为空")
    if source_type not in ("git", "web_url"):
        raise HTTPException(400, f"不支持的数据源类型: {source_type}")

    ds = DataSource(
        kb_id=kb_id,
        name=name,
        source_type=source_type,
        config=json.dumps(config, ensure_ascii=False),
        sync_cron=sync_cron,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds.to_dict()


@router.get("/{source_id}")
async def get_data_source(
    source_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取数据源详情"""
    ds = db.query(DataSource).get(source_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    require_kb_access(db, user, ds.kb_id, "viewer")
    return ds.to_dict()


@router.put("/{source_id}")
async def update_data_source(
    source_id: str,
    data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新数据源配置"""
    ds = db.query(DataSource).get(source_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    require_kb_access(db, user, ds.kb_id, "editor")

    for key in ["name", "config", "sync_cron"]:
        if key in data:
            val = data[key]
            if key == "config":
                val = json.dumps(val, ensure_ascii=False)
            setattr(ds, key, val)
    db.commit()
    db.refresh(ds)
    return ds.to_dict()


@router.delete("/{source_id}")
async def delete_data_source(
    source_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除数据源"""
    ds = db.query(DataSource).get(source_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    require_kb_access(db, user, ds.kb_id, "admin")
    db.delete(ds)
    db.commit()
    return {"message": "已删除"}


@router.post("/{source_id}/sync")
async def trigger_sync(
    source_id: str,
    request=None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动触发同步"""
    ds = db.query(DataSource).get(source_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    require_kb_access(db, user, ds.kb_id, "editor")

    if ds.sync_status == SyncStatus.SYNCING:
        raise HTTPException(400, "正在同步中，请稍后再试")

    # 后台线程执行
    t = threading.Thread(
        target=lambda: _run_sync(source_id),
        daemon=True,
    )
    t.start()

    return {"message": "同步已启动", "source_id": source_id}


def _run_sync(source_id: str):
    """后台同步入口"""
    from app.core.ds_engine import sync_data_source
    db = SessionLocal()
    try:
        sync_data_source(source_id, db)
    except Exception as e:
        print(f"[DS Sync] 后台同步异常: {e}")
    finally:
        db.close()


@router.post("/{source_id}/test")
async def test_connection(
    source_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """测试数据源连接"""
    ds = db.query(DataSource).get(source_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    require_kb_access(db, user, ds.kb_id, "viewer")

    from app.core.ds_adapters import get_adapter
    adapter = get_adapter(ds.source_type)
    config = json.loads(ds.config) if ds.config else {}
    config["source_id"] = source_id
    result = adapter.test_connection(config)
    return result


@router.post("/test")
async def test_new_connection(
    data: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """测试新数据源连接（创建前）"""
    source_type = data.get("source_type", "").strip()
    config = data.get("config", {})
    if not source_type:
        raise HTTPException(400, "source_type 不能为空")

    from app.core.ds_adapters import get_adapter
    adapter = get_adapter(source_type)
    result = adapter.test_connection(config)
    return result
