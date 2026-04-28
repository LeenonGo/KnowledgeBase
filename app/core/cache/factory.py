"""缓存工厂 — 根据配置创建缓存实例"""

import os


def create_cache():
    """根据环境变量或配置创建缓存实例"""
    backend = os.environ.get("CACHE_BACKEND", "memory")

    if backend == "redis":
        try:
            from app.core.cache.redis_impl import RedisCache
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            return RedisCache(redis_url)
        except ImportError:
            print("[Cache] redis 包未安装，降级为内存缓存")
            from app.core.cache.memory import MemoryCache
            return MemoryCache()
        except Exception as e:
            print(f"[Cache] Redis 连接失败({e})，降级为内存缓存")
            from app.core.cache.memory import MemoryCache
            return MemoryCache()
    else:
        from app.core.cache.memory import MemoryCache
        return MemoryCache()
