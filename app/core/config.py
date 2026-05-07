"""统一配置加载 — 带 mtime 缓存，所有模块共用"""

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
MODELS_PATH = CONFIG_DIR / "models.json"
PROMPTS_PATH = CONFIG_DIR / "prompts.json"

# ─── 通用 mtime 缓存 ────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}  # path -> (mtime, data)


def _load_cached(path: Path) -> dict:
    """按 mtime 缓存读取 JSON 文件，文件未变则直接返回缓存"""
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    cached = _cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[str(path)] = (mtime, data)
    return data


def load_models_config() -> dict:
    """加载 models.json 完整配置"""
    return _load_cached(MODELS_PATH)


def load_prompts_config() -> dict:
    """加载 prompts.json 完整配置"""
    return _load_cached(PROMPTS_PATH)


def get_llm_config() -> dict:
    """获取 LLM 子配置"""
    return load_models_config().get("llm", {})


def get_embedding_config() -> dict:
    """获取 Embedding 子配置"""
    return load_models_config().get("embedding", {})


def get_reranker_config() -> dict:
    """获取 Reranker 子配置"""
    return load_models_config().get("reranker", {})


# ─── 向后兼容 ──────────────────────────────────
def load_config():
    """加载完整模型配置（Pydantic schema）"""
    from app.models.schema import ModelsConfig
    return ModelsConfig(**load_models_config())
