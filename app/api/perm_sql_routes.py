"""SQL 表级权限管理 API"""

import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api/sql/permissions", tags=["SQL权限管理"])


class PermCreate(BaseModel):
    role: str = Field(..., min_length=1, max_length=32)
    table_name: str = Field(..., min_length=1, max_length=64)
    can_query: bool = Field(default=True)
    max_rows: int = Field(default=500, ge=0, le=10000)
    columns_deny: str = Field(default="")


class PermUpdate(BaseModel):
    can_query: Optional[bool] = None
    max_rows: Optional[int] = None
    columns_deny: Optional[str] = None


class BatchPermUpdate(BaseModel):
    """批量更新某角色的权限"""
    role: str
    permissions: List[dict]  # [{table_name, can_query, max_rows, columns_deny}]


@router.get("")
async def list_permissions(
    role: str = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """获取权限列表"""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "仅管理员可管理权限")

    from app.models.models import SqlTablePermission

    q = db.query(SqlTablePermission)
    if role:
        q = q.filter(SqlTablePermission.role == role)

    perms = q.order_by(SqlTablePermission.role, SqlTablePermission.table_name).all()

    # 获取所有可用的角色和表
    roles = list(set(p.role for p in perms))
    tables = list(set(p.table_name for p in perms))

    return {
        "items": [{
            "id": p.id,
            "role": p.role,
            "table_name": p.table_name,
            "can_query": p.can_query,
            "max_rows": p.max_rows,
            "columns_deny": p.columns_deny,
        } for p in perms],
        "roles": roles,
        "tables": tables,
    }


@router.post("")
async def create_permission(
    req: PermCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """创建权限"""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "仅管理员可管理权限")

    from app.models.models import SqlTablePermission

    exists = db.query(SqlTablePermission).filter(
        SqlTablePermission.role == req.role,
        SqlTablePermission.table_name == req.table_name,
    ).first()
    if exists:
        raise HTTPException(400, f"{req.role} 对 {req.table_name} 的权限已存在")

    perm = SqlTablePermission(
        role=req.role,
        table_name=req.table_name,
        can_query=req.can_query,
        max_rows=req.max_rows,
        columns_deny=req.columns_deny,
    )
    db.add(perm)
    db.commit()

    log_audit(db, user, "perm_create", f"{req.role}:{req.table_name}", "创建权限", "success")
    return {"id": perm.id, "message": "创建成功"}


@router.put("/{perm_id}")
async def update_permission(
    perm_id: int,
    req: PermUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """更新权限"""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "仅管理员可管理权限")

    from app.models.models import SqlTablePermission

    perm = db.query(SqlTablePermission).filter(SqlTablePermission.id == perm_id).first()
    if not perm:
        raise HTTPException(404, "权限记录不存在")

    if req.can_query is not None:
        perm.can_query = req.can_query
    if req.max_rows is not None:
        perm.max_rows = req.max_rows
    if req.columns_deny is not None:
        perm.columns_deny = req.columns_deny

    db.commit()
    log_audit(db, user, "perm_update", f"{perm.role}:{perm.table_name}", "更新权限", "success")
    return {"message": "更新成功"}


@router.put("/batch/{role}")
async def batch_update_permissions(
    role: str,
    req: BatchPermUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """批量更新某角色的所有权限"""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "仅管理员可管理权限")

    from app.models.models import SqlTablePermission

    # 删除旧权限
    db.query(SqlTablePermission).filter(SqlTablePermission.role == role).delete()

    # 插入新权限
    for p in req.permissions:
        perm = SqlTablePermission(
            role=role,
            table_name=p.get("table_name", ""),
            can_query=p.get("can_query", True),
            max_rows=p.get("max_rows", 500),
            columns_deny=p.get("columns_deny", ""),
        )
        db.add(perm)

    db.commit()
    log_audit(db, user, "perm_batch_update", role, f"批量更新{len(req.permissions)}条权限", "success")
    return {"message": f"已更新 {len(req.permissions)} 条权限"}


@router.delete("/{perm_id}")
async def delete_permission(
    perm_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """删除权限"""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "仅管理员可管理权限")

    from app.models.models import SqlTablePermission

    perm = db.query(SqlTablePermission).filter(SqlTablePermission.id == perm_id).first()
    if not perm:
        raise HTTPException(404, "权限记录不存在")

    db.delete(perm)
    db.commit()
    log_audit(db, user, "perm_delete", f"{perm.role}:{perm.table_name}", "删除权限", "success")
    return {"message": "删除成功"}
