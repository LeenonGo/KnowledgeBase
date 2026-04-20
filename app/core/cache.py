"""查询缓存 — 内存缓存，支持 TTL 过期"""

import hashlib
import time
import threading
from typing import Any


class QueryCache:
    """线程安全的内存缓存"""

    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        """
        Args:
            default_ttl: 默认过期时间（秒）
            max_size: 最大缓存条数
        """
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size

    def _make_key(self, question: str, kb_id: str = None) -> str:
        """生成缓存 key"""
        raw = f"{kb_id or 'all'}::{question}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, question: str, kb_id: str = None) -> Any | None:
        """获取缓存"""
        key = self._make_key(question, kb_id)
        with self._lock:
            if key not in self._cache:
                return None
            expire_time, value = self._cache[key]
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return value

    def set(self, question: str, value: Any, kb_id: str = None, ttl: int = None):
        """设置缓存"""
        key = self._make_key(question, kb_id)
        expire = time.time() + (ttl or self._default_ttl)
        with self._lock:
            # 超过最大条数时清理过期项
            if len(self._cache) >= self._max_size:
                self._cleanup()
            self._cache[key] = (expire, value)

    def invalidate_kb(self, kb_id: str):
        """使指定知识库的所有缓存失效"""
        with self._lock:
            # 简单实现：全量清理（生产环境可用前缀树优化）
            to_remove = []
            for key, (expire, _) in self._cache.items():
                if time.time() > expire:
                    to_remove.append(key)
            for key in to_remove:
                del self._cache[key]

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def _cleanup(self):
        """清理过期和最旧的条目"""
        now = time.time()
        expired = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[self._cache_key_for(k)]

        # 如果还是超限，删除最旧的
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
            for k in sorted_keys[:self._max_size // 4]:
                del self._cache[k]

    def stats(self) -> dict:
        """缓存统计"""
        with self._lock:
            now = time.time()
            active = sum(1 for exp, _ in self._cache.values() if exp > now)
            return {"total": len(self._cache), "active": active, "expired": len(self._cache) - active}


# 全局缓存实例
query_cache = QueryCache(default_ttl=3600, max_size=1000)
