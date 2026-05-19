"""工具管理 API — 插件化工具注册"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api/tools", tags=["工具管理"])


class ToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="")
    parameters: dict = Field(default={"type": "object", "properties": {}, "required": []})
    handler: str = Field(..., min_length=1, max_length=256)
    category: str = Field(default="general")
    sort_order: int = Field(default=0)


class ToolUpdate(BaseModel):
    description: Optional[str] = None
    parameters: Optional[dict] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


@router.get("")
async def list_tools(
    category: str = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """获取工具列表"""
    from app.models.models import ToolDef

    q = db.query(ToolDef)
    if category:
        q = q.filter(ToolDef.category == category)

    tools = q.order_by(ToolDef.category, ToolDef.sort_order).all()

    return {
        "items": [{
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "parameters": json.loads(t.parameters) if t.parameters else {},
            "handler": t.handler,
            "category": t.category,
            "is_active": t.is_active,
            "is_builtin": t.is_builtin,
            "sort_order": t.sort_order,
            "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        } for t in tools],
        "categories": list(set(t.category for t in tools)),
    }


@router.post("")
async def create_tool(
    req: ToolCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """创建工具（仅管理员）"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(403, "权限不足")

    from app.models.models import ToolDef

    # 检查名称是否重复
    exists = db.query(ToolDef).filter(ToolDef.name == req.name).first()
    if exists:
        raise HTTPException(400, f"工具名 {req.name} 已存在")

    # 验证 handler 格式
    if ":" not in req.handler:
        raise HTTPException(400, "handler 格式应为 module:function，如 app.core.tools:search_kb")

    tool = ToolDef(
        name=req.name,
        description=req.description,
        parameters=json.dumps(req.parameters, ensure_ascii=False),
        handler=req.handler,
        category=req.category,
        sort_order=req.sort_order,
        is_active=True,
        is_builtin=False,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)

    # 清除工具注册中心缓存
    from app.core.tools import registry
    registry.clear_cache()

    log_audit(db, user, "tool_create", req.name, "创建工具", "success")
    return {"id": tool.id, "message": "创建成功"}


@router.put("/{tool_id}")
async def update_tool(
    tool_id: int,
    req: ToolUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """更新工具（仅管理员）"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(403, "权限不足")

    from app.models.models import ToolDef

    tool = db.query(ToolDef).filter(ToolDef.id == tool_id).first()
    if not tool:
        raise HTTPException(404, "工具不存在")

    if req.description is not None:
        tool.description = req.description
    if req.parameters is not None:
        tool.parameters = json.dumps(req.parameters, ensure_ascii=False)
    if req.category is not None:
        tool.category = req.category
    if req.is_active is not None:
        tool.is_active = req.is_active
    if req.sort_order is not None:
        tool.sort_order = req.sort_order

    db.commit()

    # 清除缓存
    from app.core.tools import registry
    registry.clear_cache()

    log_audit(db, user, "tool_update", tool.name, "更新工具", "success")
    return {"message": "更新成功"}


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """删除工具（仅管理员，内置工具不可删）"""
    if user.get("role") not in ("super_admin", "kb_admin"):
        raise HTTPException(403, "权限不足")

    from app.models.models import ToolDef

    tool = db.query(ToolDef).filter(ToolDef.id == tool_id).first()
    if not tool:
        raise HTTPException(404, "工具不存在")
    if tool.is_builtin:
        raise HTTPException(400, "内置工具不可删除，可以禁用")

    db.delete(tool)
    db.commit()

    # 清除缓存
    from app.core.tools import registry
    registry.clear_cache()

    log_audit(db, user, "tool_delete", tool.name, "删除工具", "success")
    return {"message": "删除成功"}
