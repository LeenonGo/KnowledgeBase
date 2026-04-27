"""用户管理 API"""

import json
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import User
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api", tags=["用户"])



@router.get("/users")
async def get_users(page: int = 1, page_size: int = 10, role: str = None,
                    db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [{
            "id": u.id, "username": u.username, "display_name": u.display_name,
            "email": u.email, "role": u.role, "department_id": u.department_id,
            "department_name": u.department.name if u.department else "",
            "position": u.position, "status": u.status,
            "last_login": str(u.last_login) if u.last_login else None,
        } for u in users]
    }


@router.post("/users")
async def create_user(data: dict, request: Request,
                      db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from werkzeug.security import generate_password_hash
    from app.api.auth_routes import validate_password_strength
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(400, "用户名已存在")
    pw = data.get("password", "")
    if pw:
        err = validate_password_strength(pw)
        if err:
            raise HTTPException(400, err)
    else:
        pw = "admin123"  # 默认密码（首次登录强制改密场景）
    new_user = User(
        username=data["username"], display_name=data["display_name"],
        email=data.get("email", ""),
        password_hash=generate_password_hash(pw),
        department_id=data.get("department_id") or None,
        position=data.get("position", ""), role=data.get("role", "user"),
        status="active",
    )
    db.add(new_user)
    db.commit()
    log_audit(db, user, "create_user", data["username"], f"role={new_user.role}", "success",
               request.client.host if request.client else "")
    return {"id": new_user.id, "username": new_user.username}


@router.put("/users/{user_id}")
async def update_user(user_id: str, data: dict, request: Request,
                      db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    for field in ("display_name", "email", "position", "department_id", "role", "status"):
        if field in data:
            setattr(target, field, data[field] or None if field == "department_id" else data[field])
    if "password" in data and data["password"]:
        from werkzeug.security import generate_password_hash
        from app.api.auth_routes import validate_password_strength
        err = validate_password_strength(data["password"])
        if err:
            raise HTTPException(400, err)
        target.password_hash = generate_password_hash(data["password"])
    db.commit()
    log_audit(db, user, "update_user", target.username,
               json.dumps(data, ensure_ascii=False), "success",
               request.client.host if request.client else "")
    return {"id": target.id, "username": target.username}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request,
                      db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    target.status = "disabled"
    db.commit()
    log_audit(db, user, "delete_user", target.username, "禁用", "success",
               request.client.host if request.client else "")
    return {"message": "已禁用"}
