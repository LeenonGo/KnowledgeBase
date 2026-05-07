"""Redis 缓存实现 — 可选后端，需要 redis 包"""

import hashlib
import json
from typing import Any

try:
    import redis
except ImportError:
    redis = None


class RedisCache:
    """Redis 缓存，多实例共享"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 default_ttl: int = 3600, prefix: str = "kb:"):
        if redis is None:
            raise ImportError("需要安装 redis 包: pip install redis")
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._default_ttl = default_ttl
        self._prefix = prefix
        # 测试连接
        self._client.ping()

    def make_key(self, question: str, kb_id: str = None, user_id: str = None,
                 use_agent: bool = False, use_polish: bool = False, use_rewrite: bool = False) -> str:
        mode = f"{'ag' if use_agent else 'nag'}:{'pl' if use_polish else 'npl'}:{'rw' if use_rewrite else 'nrw'}"
        raw = f"{user_id or 'anon'}::{kb_id or 'all'}::{mode}::{question}"
        return self._prefix + hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        data = self._client.get(key)
        if data is None:
            return None
        return json.loads(data)

    def set(self, key: str, value: Any, ttl: int = None):
        self._client.setex(key, ttl or self._default_ttl, json.dumps(value, ensure_ascii=False))

    def delete(self, key: str):
        self._client.delete(key)

    def clear(self):
        """清空缓存 — 用 SCAN 迭代删除，避免 KEYS 阻塞 Redis"""
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=self._prefix + "*", count=100)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break

    def stats(self) -> dict:
        """统计信息 — 用 SCAN 计数，避免 KEYS 阻塞"""
        total = 0
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=self._prefix + "*", count=100)
            total += len(keys)
            if cursor == 0:
                break
        return {"backend": "redis", "total": total, "active": total, "expired": 0}
