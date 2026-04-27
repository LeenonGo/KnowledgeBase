"""登录 & 用户信息 API"""

import json
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import create_token, verify_password
from app.models.models import User
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api", tags=["认证"])

_CST = timezone(timedelta(hours=8))


def validate_password_strength(pw: str) -> str:
    """校验密码复杂度，返回错误信息（空字符串=通过）"""
    if len(pw) < 8:
        return "密码至少需要 8 位"
    if not re.search(r"[a-zA-Z]", pw):
        return "密码需包含字母"
    if not re.search(r"[0-9]", pw):
        return "密码需包含数字"
    return ""


@router.post("/login")
async def login(data: dict, request: Request, db: Session = Depends(get_db)):
    username = data.get("username", "")
    password = data.get("password", "")
    ip = request.client.host if request.client else ""

    user = db.query(User).filter(User.username == username).first()
    if not user or user.status != "active":
        log_audit(db, None, "login", username, "用户不存在或已禁用", "failure", ip)
        raise HTTPException(401, "用户名或密码错误")

    if not verify_password(password, user.password_hash):
        log_audit(db, {"sub": user.id, "username": user.username}, "login", username, "密码错误", "failure", ip)
        raise HTTPException(401, "用户名或密码错误")

    user.last_login = datetime.now(_CST)
    db.commit()

    token = create_token(user.id, user.username, user.role)
    log_audit(db, {"sub": user.id, "username": user.username}, "login", username, "登录成功", "success", ip)

    return {
        "token": token,
        "user": {
            "id": user.id, "username": user.username,
            "display_name": user.display_name, "role": user.role,
        }
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(404, "用户不存在")
    return {
        "id": db_user.id, "username": db_user.username,
        "display_name": db_user.display_name, "role": db_user.role,
        "department_id": db_user.department_id,
    }


@router.post("/change-password")
async def change_password(data: dict, request: Request,
                          db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """修改当前用户密码"""
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        raise HTTPException(400, "请填写当前密码和新密码")

    # 校验新密码复杂度
    err = validate_password_strength(new_password)
    if err:
        raise HTTPException(400, err)

    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(404, "用户不存在")

    if not verify_password(old_password, db_user.password_hash):
        log_audit(db, user, "change_password", db_user.username, "当前密码错误", "failure",
                  request.client.host if request.client else "")
        raise HTTPException(400, "当前密码错误")

    from werkzeug.security import generate_password_hash
    db_user.password_hash = generate_password_hash(new_password)
    db.commit()

    log_audit(db, user, "change_password", db_user.username, "密码修改成功", "success",
              request.client.host if request.client else "")
    return {"message": "密码修改成功"}
