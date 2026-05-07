"""统一时间工具 — 所有模块共用，避免各自定义 _CST"""

from datetime import datetime, timezone, timedelta

# Asia/Shanghai UTC+8
CST = timezone(timedelta(hours=8))


def now_cst() -> datetime:
    """返回当前 CST 时间"""
    return datetime.now(CST)


def utcnow() -> datetime:
    """返回当前 UTC 时间（JWT 等标准场景用）"""
    return datetime.now(timezone.utc)
