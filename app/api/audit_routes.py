"""审计日志 API — 仅管理员可访问"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import AuditLog
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["审计"])


@router.get("/audit-logs")
async def get_audit_logs(
    action: str = None, username: str = None,
    page: int = 1, page_size: int = 20,
    db: Session = Depends(get_db), user: dict = Depends(get_current_user),
):
    # 仅 super_admin 可查看审计日志
    if user.get("role") != "super_admin":
        raise HTTPException(403, "无权查看审计日志")

    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if username:
        q = q.filter(AuditLog.username == username)
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [{
        "id": l.id, "username": l.username, "action": l.action,
        "resource": l.resource, "detail": l.detail,
        "ip_address": l.ip_address, "status": l.status,
        "created_at": str(l.created_at),
    } for l in logs]}
