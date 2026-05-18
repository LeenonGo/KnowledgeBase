"""数据源适配器工厂 + 注册表"""

from app.core.ds_adapters.git_adapter import GitAdapter
from app.core.ds_adapters.web_adapter import WebAdapter

# 适配器注册表
ADAPTER_REGISTRY = {
    "git": GitAdapter,
    "web_url": WebAdapter,
}


def get_adapter(source_type: str):
    """获取适配器实例"""
    cls = ADAPTER_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(f"不支持的数据源类型: {source_type}")
    return cls()


__all__ = ["ADAPTER_REGISTRY", "get_adapter", "GitAdapter", "WebAdapter"]
