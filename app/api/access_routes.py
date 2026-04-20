"""知识库授权管理 API（部门 + 个人）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import KBDepartmentAccess, KBUserAccess, User
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["授权"])


# ─── 部门授权 ────────────────────────────────────

@router.get("/kb-access")
async def get_kb_access(kb_id: str = None,
                        db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    q = db.query(KBDepartmentAccess)
    if kb_id:
        q = q.filter(KBDepartmentAccess.kb_id == kb_id)
    records = q.all()
    return [{"id": r.id, "kb_id": r.kb_id, "department_id": r.department_id, "role": r.role}
            for r in records]


@router.post("/kb-access")
async def set_kb_access(data: dict,
                        db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    kb_id, dept_id, role = data["kb_id"], data["department_id"], data["role"]
    existing = db.query(KBDepartmentAccess).filter(
        KBDepartmentAccess.kb_id == kb_id,
        KBDepartmentAccess.department_id == dept_id,
    ).first()
    if existing:
        existing.role = role
    else:
        record = KBDepartmentAccess(kb_id=kb_id, department_id=dept_id,
                                    role=role, created_by=user["sub"])
        db.add(record)
    db.commit()
    return {"message": "已更新"}


@router.delete("/kb-access")
async def remove_kb_access(kb_id: str, department_id: str,
                           db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    record = db.query(KBDepartmentAccess).filter(
        KBDepartmentAccess.kb_id == kb_id,
        KBDepartmentAccess.department_id == department_id,
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return {"message": "已删除"}


# ─── 个人授权 ────────────────────────────────────

@router.get("/kb-user-access")
async def get_kb_user_access(kb_id: str = None,
                             db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    q = db.query(KBUserAccess)
    if kb_id:
        q = q.filter(KBUserAccess.kb_id == kb_id)
    records = q.all()
    result = []
    for r in records:
        u = db.query(User).filter(User.id == r.user_id).first()
        result.append({
            "id": r.id, "kb_id": r.kb_id, "user_id": r.user_id,
            "username": u.username if u else r.user_id,
            "display_name": u.display_name if u else "",
            "department_name": u.department.name if u and u.department else "",
            "role": r.role,
        })
    return result


@router.post("/kb-user-access")
async def set_kb_user_access(data: dict,
                             db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    kb_id, user_id, role = data["kb_id"], data["user_id"], data["role"]
    existing = db.query(KBUserAccess).filter(
        KBUserAccess.kb_id == kb_id,
        KBUserAccess.user_id == user_id,
    ).first()
    if existing:
        existing.role = role
    else:
        record = KBUserAccess(kb_id=kb_id, user_id=user_id,
                              role=role, created_by=user["sub"])
        db.add(record)
    db.commit()
    return {"message": "已更新"}


@router.delete("/kb-user-access")
async def remove_kb_user_access(kb_id: str, user_id: str,
                                db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    record = db.query(KBUserAccess).filter(
        KBUserAccess.kb_id == kb_id,
        KBUserAccess.user_id == user_id,
    ).first()
    if record:
        db.delete(record)
        db.commit()
    return {"message": "已删除"}
