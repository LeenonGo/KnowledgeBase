"""认证依赖 + 权限检查 — 所有路由模块共享"""

import time
import threading

from fastapi import HTTPException, Request, Header, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import verify_token
from app.models.models import User, KBDepartmentAccess, AuditLog


PUBLIC_PATHS = {"/api/login"}

# ─── 用户状态缓存（避免每次请求都查库）───────────────
# key: user_id -> (timestamp, is_active)
_user_status_cache: dict[str, tuple[float, bool]] = {}
_user_cache_lock = threading.Lock()
_USER_CACHE_TTL = 60  # 60 秒内信任缓存


def _is_user_active(db: Session, user_id: str) -> bool:
    """带缓存的用户状态查询"""
    now = time.time()
    with _user_cache_lock:
        cached = _user_status_cache.get(user_id)
        if cached and now - cached[0] < _USER_CACHE_TTL:
            return cached[1]

    # 缓存未命中，查库
    user = db.query(User.status).filter(User.id == user_id).first()
    is_active = bool(user and user[0] == "active")
    with _user_cache_lock:
        _user_status_cache[user_id] = (now, is_active)
    return is_active


def invalidate_user_cache(user_id: str):
    """使用户状态缓存失效（禁用/启用用户时调用）"""
    with _user_cache_lock:
        _user_status_cache.pop(user_id, None)


def log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    """写入审计日志（共用）"""
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


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

    # 用缓存查用户状态，而非每次全量查询
    if not _is_user_active(db, payload["sub"]):
        raise HTTPException(status_code=401, detail="账号已被禁用")

    return payload


def get_current_user_strict(
    request: Request,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict:
    """严格认证 — 必须有有效 token（不接受 None），用于敏感操作"""
    user = get_current_user(request, authorization, db)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return user


# ─── 权限检查 ────────────────────────────────────

def _get_user_dept_id(db: Session, user_id: str) -> str | None:
    u = db.query(User.department_id).filter(User.id == user_id).first()
    return u[0] if u else None


def _get_dept_ancestor_ids(db: Session, dept_path: str) -> set[str]:
    """从部门路径提取所有祖先部门 ID（含自身）"""
    from app.models.models import Department
    dept_ids = set()
    path_parts = dept_path.strip("/").split("/")
    current_path = ""
    for part in path_parts:
        current_path += "/" + part
        d = db.query(Department.id).filter(Department.path == current_path).first()
        if d:
            dept_ids.add(d.id)
    return dept_ids


def get_kb_role(db: Session, user: dict, kb_id: str) -> str | None:
    """获取用户对某知识库的角色（部门 + 个人授权合并）"""
    role = user.get("role")
    if role == "super_admin":
        return "admin"

    dept_id = _get_user_dept_id(db, user["sub"])

    best_level = 0
    best_role = None
    levels = {"admin": 3, "editor": 2, "viewer": 1}

    # 部门授权（含父部门继承）
    if dept_id:
        from app.models.models import Department
        dept = db.query(Department.path).filter(Department.id == dept_id).first()
        if dept and dept.path:
            dept_ids = _get_dept_ancestor_ids(db, dept.path)
            if dept_ids:
                rows = db.query(KBDepartmentAccess).filter(
                    KBDepartmentAccess.kb_id == kb_id,
                    KBDepartmentAccess.department_id.in_(dept_ids),
                ).all()
                for da in rows:
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

    # kb_admin 角色用户对有授权的 KB 至少有 editor 权限
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
    """返回用户可访问的 kb_id 列表，super_admin 返回 None（全部）。"""
    if user.get("role") == "super_admin":
        return None

    dept_id = _get_user_dept_id(db, user["sub"])
    kb_ids = set()

    # 部门授权（含父部门继承）
    if dept_id:
        from app.models.models import Department
        dept = db.query(Department.path).filter(Department.id == dept_id).first()
        if dept and dept.path:
            dept_ids = _get_dept_ancestor_ids(db, dept.path)
            if dept_ids:
                rows = db.query(KBDepartmentAccess.kb_id).filter(
                    KBDepartmentAccess.department_id.in_(dept_ids)
                ).all()
                kb_ids.update(r[0] for r in rows)

    # 个人授权
    from app.models.models import KBUserAccess
    rows = db.query(KBUserAccess.kb_id).filter(
        KBUserAccess.user_id == user["sub"]
    ).all()
    kb_ids.update(r[0] for r in rows)

    return list(kb_ids) if kb_ids else []
