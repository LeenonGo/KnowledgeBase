"""Skill 管理 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
import json

from app.api.deps import get_db, get_current_user
from app.models.models import Skill, SkillExecutionLog
from app.core.skill_registry import skill_registry

router = APIRouter(prefix="/api/skills", tags=["Skills"])


# ─── 请求模型 ────────────────────────────────────
class SkillCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    category: str = "general"
    icon: str = "⚡"
    parameters_schema: str = "{}"
    return_schema: str = "{}"
    handler_type: str = "python"
    handler_config: str = "{}"
    required_role: str = "user"
    rate_limit: int = 100
    timeout_seconds: int = 30


class SkillUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    parameters_schema: Optional[str] = None
    return_schema: Optional[str] = None
    handler_type: Optional[str] = None
    handler_config: Optional[str] = None
    required_role: Optional[str] = None
    rate_limit: Optional[int] = None
    timeout_seconds: Optional[int] = None


class SkillTestRequest(BaseModel):
    arguments: dict = {}


# ─── Skill 列表 ──────────────────────────────────
@router.get("")
async def list_skills(
    category: Optional[str] = None,
    enabled_only: bool = True,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取 Skill 列表"""
    query = db.query(Skill)

    if category:
        query = query.filter(Skill.category == category)
    if enabled_only:
        query = query.filter(Skill.is_enabled == True)

    skills = query.order_by(Skill.category, Skill.name).all()

    return [{
        "id": s.id,
        "name": s.name,
        "display_name": s.display_name,
        "description": s.description,
        "category": s.category,
        "icon": s.icon,
        "version": s.version,
        "author": s.author,
        "handler_type": s.handler_type,
        "required_role": s.required_role,
        "is_enabled": s.is_enabled,
        "is_builtin": s.is_builtin,
        "usage_count": s.usage_count,
        "avg_latency_ms": round(s.avg_latency_ms, 1) if s.avg_latency_ms else 0,
        "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    } for s in skills]


# ─── Skill 详情 ──────────────────────────────────
@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取 Skill 详情"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    return {
        "id": skill.id,
        "name": skill.name,
        "display_name": skill.display_name,
        "description": skill.description,
        "category": skill.category,
        "icon": skill.icon,
        "version": skill.version,
        "author": skill.author,
        "parameters_schema": skill.parameters_schema,
        "return_schema": skill.return_schema,
        "handler_type": skill.handler_type,
        "handler_config": skill.handler_config,
        "required_role": skill.required_role,
        "rate_limit": skill.rate_limit,
        "timeout_seconds": skill.timeout_seconds,
        "is_enabled": skill.is_enabled,
        "is_builtin": skill.is_builtin,
        "usage_count": skill.usage_count,
        "avg_latency_ms": round(skill.avg_latency_ms, 1) if skill.avg_latency_ms else 0,
        "last_used_at": skill.last_used_at.isoformat() if skill.last_used_at else None,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


# ─── 创建 Skill ──────────────────────────────────
@router.post("")
async def create_skill(
    data: SkillCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """创建自定义 Skill"""
    # 检查名称唯一性
    existing = db.query(Skill).filter(Skill.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Skill 名称已存在")

    # 验证 JSON
    try:
        json.loads(data.parameters_schema)
        json.loads(data.handler_config)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 格式错误: {e}")

    skill = Skill(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        category=data.category,
        icon=data.icon,
        parameters_schema=data.parameters_schema,
        return_schema=data.return_schema,
        handler_type=data.handler_type,
        handler_config=data.handler_config,
        required_role=data.required_role,
        rate_limit=data.rate_limit,
        timeout_seconds=data.timeout_seconds,
        is_builtin=False,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    skill_registry.clear_cache()

    return {"id": skill.id, "name": skill.name, "message": "创建成功"}


# ─── 更新 Skill ──────────────────────────────────
@router.put("/{skill_id}")
async def update_skill(
    skill_id: str,
    data: SkillUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """更新 Skill"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    if skill.is_builtin:
        raise HTTPException(status_code=400, detail="内置 Skill 不可修改")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(skill, field, value)

    db.commit()
    skill_registry.clear_cache()

    return {"message": "更新成功"}


# ─── 删除 Skill ──────────────────────────────────
@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """删除自定义 Skill"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    if skill.is_builtin:
        raise HTTPException(status_code=400, detail="内置 Skill 不可删除")

    db.delete(skill)
    db.commit()
    skill_registry.clear_cache()

    return {"message": "删除成功"}


# ─── 启用/禁用 Skill ─────────────────────────────
@router.post("/{skill_id}/toggle")
async def toggle_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """启用/禁用 Skill"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    skill.is_enabled = not skill.is_enabled
    db.commit()
    skill_registry.clear_cache()

    return {"is_enabled": skill.is_enabled, "message": f"已{'启用' if skill.is_enabled else '禁用'}"}


# ─── 测试 Skill ──────────────────────────────────
@router.post("/{skill_id}/test")
async def test_skill(
    skill_id: str,
    data: SkillTestRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """测试 Skill 执行"""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    result = skill_registry.execute(
        name=skill.name,
        arguments=data.arguments,
        db=db,
        user=user,
    )

    return {"result": result, "skill": skill.name}


# ─── Skill 使用统计 ──────────────────────────────
@router.get("/stats/overview")
async def skill_stats(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Skill 使用统计概览"""
    from sqlalchemy import func

    total = db.query(Skill).count()
    enabled = db.query(Skill).filter(Skill.is_enabled == True).count()
    builtin = db.query(Skill).filter(Skill.is_builtin == True).count()

    # Top 10 热门 Skill
    top_skills = db.query(Skill).filter(
        Skill.usage_count > 0
    ).order_by(Skill.usage_count.desc()).limit(10).all()

    # 按分类统计
    category_stats = db.query(
        Skill.category, func.count(Skill.id)
    ).group_by(Skill.category).all()

    return {
        "total": total,
        "enabled": enabled,
        "builtin": builtin,
        "custom": total - builtin,
        "top_skills": [{"name": s.name, "display_name": s.display_name,
                        "usage_count": s.usage_count} for s in top_skills],
        "by_category": {cat: cnt for cat, cnt in category_stats},
    }


# ─── Skill 分类列表 ──────────────────────────────
@router.get("/meta/categories")
async def skill_categories(
    db: Session = Depends(get_db),
):
    """获取 Skill 分类列表"""
    from sqlalchemy import func
    categories = db.query(
        Skill.category, func.count(Skill.id)
    ).filter(Skill.is_enabled == True).group_by(Skill.category).all()

    return [{"name": cat, "count": cnt} for cat, cnt in categories]
