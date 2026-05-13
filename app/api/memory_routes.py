"""用户记忆 & FAQ 管理 API"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, log_audit
from app.core.memory_service import (
    get_user_memories, delete_user_memory, get_memory_stats,
    get_all_faqs, approve_faq, reject_faq, delete_faq,
    get_faq_stats, decay_faqs,
)

router = APIRouter(prefix="/api", tags=["记忆 & FAQ"])


# ═══════════════════════════════════════════════════════════
# 用户记忆
# ═══════════════════════════════════════════════════════════

@router.get("/memory")
async def list_user_memories(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有记忆"""
    memories = get_user_memories(db, user["sub"])
    stats = get_memory_stats(db, user["sub"])
    return {"memories": memories, "stats": stats}


@router.delete("/memory/{memory_id}")
async def remove_user_memory(
    memory_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除单条记忆"""
    if not delete_user_memory(db, memory_id, user["sub"]):
        raise HTTPException(status_code=404, detail="记忆不存在")
    log_audit(db, user, "memory_delete", memory_id, "删除记忆", "success")
    return {"message": "已删除"}


@router.post("/memory/decay")
async def run_memory_decay(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动执行记忆衰减（管理员用）"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    from app.core.memory_service import decay_memories
    decay_memories(db)
    log_audit(db, user, "memory_decay", "", "手动衰减记忆", "success")
    return {"message": "衰减完成"}


@router.get("/memory/stats")
async def memory_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记忆统计"""
    return get_memory_stats(db, user["sub"])


# ═══════════════════════════════════════════════════════════
# FAQ 管理
# ═══════════════════════════════════════════════════════════

@router.get("/faq")
async def list_faqs(
    kb_id: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 FAQ 列表"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        status = "approved"  # 普通用户只能看已审核的
    return get_all_faqs(db, kb_id=kb_id, status=status, page=page, page_size=page_size)


@router.get("/faq/stats")
async def faq_statistics(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FAQ 统计"""
    return get_faq_stats(db)


class FAQApproveRequest(BaseModel):
    faq_ids: list[str] = Field(..., description="FAQ ID 列表")


@router.post("/faq/{faq_id}/approve")
async def approve_faq_item(
    faq_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """审核通过 FAQ"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(status_code=403, detail="无权操作")
    if not approve_faq(db, faq_id, user["sub"]):
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    log_audit(db, user, "faq_approve", faq_id, "审核通过 FAQ", "success")
    return {"message": "已通过"}


@router.post("/faq/{faq_id}/reject")
async def reject_faq_item(
    faq_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拒绝 FAQ"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(status_code=403, detail="无权操作")
    if not reject_faq(db, faq_id):
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    log_audit(db, user, "faq_reject", faq_id, "拒绝 FAQ", "success")
    return {"message": "已拒绝"}


@router.delete("/faq/{faq_id}")
async def remove_faq(
    faq_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除 FAQ"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(status_code=403, detail="无权操作")
    if not delete_faq(db, faq_id):
        raise HTTPException(status_code=404, detail="FAQ 不存在")
    log_audit(db, user, "faq_delete", faq_id, "删除 FAQ", "success")
    return {"message": "已删除"}


@router.post("/faq/decay")
async def run_faq_decay(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动执行 FAQ 衰减（管理员用）"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    decay_faqs(db)
    log_audit(db, user, "faq_decay", "", "手动衰减 FAQ", "success")
    return {"message": "衰减完成"}
