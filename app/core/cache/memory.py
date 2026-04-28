"""内存缓存 — 线程安全，支持 TTL 过期"""

import hashlib
import time
import threading
from typing import Any


class MemoryCache:
    """线程安全的内存缓存"""

    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size

    def make_key(self, question: str, kb_id: str = None, user_id: str = None,
                 use_agent: bool = False, use_polish: bool = False, use_rewrite: bool = False) -> str:
        """构造缓存 key — 自动包含所有区分维度"""
        mode = f"{'ag' if use_agent else 'nag'}:{'pl' if use_polish else 'npl'}:{'rw' if use_rewrite else 'nrw'}"
        raw = f"{user_id or 'anon'}::{kb_id or 'all'}::{mode}::{question}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._cache:
                return None
            expire_time, value = self._cache[key]
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = None):
        expire = time.time() + (ttl or self._default_ttl)
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cleanup()
            self._cache[key] = (expire, value)

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def _cleanup(self):
        now = time.time()
        expired = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
            for k in sorted_keys[:self._max_size // 4]:
                del self._cache[k]

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            active = sum(1 for exp, _ in self._cache.values() if exp > now)
            return {"backend": "memory", "total": len(self._cache), "active": active,
                    "expired": len(self._cache) - active}
