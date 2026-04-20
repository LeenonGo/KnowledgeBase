"""部门管理 API"""

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Department, AuditLog
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["部门"])


def _log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


@router.get("/departments")
async def get_departments(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    depts = db.query(Department).filter(Department.status == "active").all()
    return [{"id": d.id, "name": d.name, "path": d.path, "parent_id": d.parent_id} for d in depts]


@router.post("/departments")
async def create_department(data: dict, request: Request,
                            db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    dept = Department(
        name=data["name"], path=data.get("path", "/" + data["name"]),
        parent_id=data.get("parent_id"), description=data.get("description", ""),
    )
    db.add(dept)
    db.commit()
    _log_audit(db, user, "create_dept", data["name"], "", "success",
               request.client.host if request.client else "")
    return {"id": dept.id, "name": dept.name}


@router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, request: Request,
                            db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    dept = db.query(Department).get(dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    dept.status = "disabled"
    db.commit()
    _log_audit(db, user, "delete_dept", dept.name, "", "success",
               request.client.host if request.client else "")
    return {"message": "已删除"}
