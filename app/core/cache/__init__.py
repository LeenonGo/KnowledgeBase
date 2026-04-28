"""缓存层 — 支持内存 / Redis 双后端"""

from app.core.cache.factory import create_cache

# 全局缓存实例（按配置创建）
query_cache = create_cache()
