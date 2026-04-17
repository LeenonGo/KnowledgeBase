"""JWT 认证 — Token 生成与验证"""

import os
import time
from datetime import datetime, timedelta

import jwt
from werkzeug.security import check_password_hash

SECRET_KEY = os.getenv("JWT_SECRET", "knowledge-base-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def create_token(user_id: str, username: str, role: str) -> str:
    """生成 JWT Token"""
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """
    验证 JWT Token。
    返回 payload dict，失败抛异常。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token 已过期")
    except jwt.InvalidTokenError:
        raise ValueError("Token 无效")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    return check_password_hash(hashed, plain)
