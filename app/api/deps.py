"""认证依赖 + 权限检查 — 所有路由模块共享"""

from fastapi import HTTPException, Request, Header, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import verify_token
from app.models.models import User, KBDepartmentAccess


PUBLIC_PATHS = {"/api/login"}


def get_current_user(
    request: Request,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict | None:
    """从 Authorization header 解析 JWT。公开路径返回 None。"""
    if request.url.path in PUBLIC_PATHS:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录，请先登录")

    token = authorization[7:]
    try:
        payload = verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="账号已被禁用")

    return payload


def _get_user_dept_id(db: Session, user_id: str) -> str | None:
    u = db.query(User.department_id).filter(User.id == user_id).first()
    return u[0] if u else None


def get_kb_role(db: Session, user: dict, kb_id: str) -> str | None:
    """获取用户对某知识库的角色（部门 + 个人授权合并）"""
    role = user.get("role")
    if role == "super_admin":
        return "admin"

    dept_id = _get_user_dept_id(db, user["sub"])

    # 合并部门授权和个人授权，取最高权限
    best_level = 0
    best_role = None
    levels = {"admin": 3, "editor": 2, "viewer": 1}

    # 部门授权
    if dept_id:
        da = db.query(KBDepartmentAccess).filter(
            KBDepartmentAccess.kb_id == kb_id,
            KBDepartmentAccess.department_id == dept_id,
        ).first()
        if da:
            lv = levels.get(da.role, 0)
            if lv > best_level:
                best_level = lv
                best_role = da.role

    # 个人授权
    from app.models.models import KBUserAccess
    ua = db.query(KBUserAccess).filter(
        KBUserAccess.kb_id == kb_id,
        KBUserAccess.user_id == user["sub"],
    ).first()
    if ua:
        lv = levels.get(ua.role, 0)
        if lv > best_level:
            best_level = lv
            best_role = ua.role

    # kb_admin 角色用户对有授权的KB至少有 editor 权限
    if role == "kb_admin" and best_role and best_level < levels["editor"]:
        best_role = "editor"

    return best_role


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

    dept_id = _get_user_dept_id(db, user["sub"])

    kb_ids = set()

    # 部门授权
    if dept_id:
        rows = db.query(KBDepartmentAccess.kb_id).filter(
            KBDepartmentAccess.department_id == dept_id
        ).all()
        kb_ids.update(r[0] for r in rows)

    # 个人授权
    from app.models.models import KBUserAccess
    rows = db.query(KBUserAccess.kb_id).filter(
        KBUserAccess.user_id == user["sub"]
    ).all()
    kb_ids.update(r[0] for r in rows)

    return list(kb_ids) if kb_ids else []
