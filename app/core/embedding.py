"""Embedding 调用 — 支持 Ollama / OpenAI 兼容接口，动态读取配置"""

import json
import time
from pathlib import Path

from openai import OpenAI

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"

# ─── 配置缓存（#5） ─────────────────────────────
_config_cache = None
_config_mtime = 0


def _load_config() -> dict:
    global _config_cache, _config_mtime
    if CONFIG_PATH.exists():
        mtime = CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and mtime == _config_mtime:
            return _config_cache
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
            _config_mtime = mtime
        return _config_cache
    return {}


def get_embedding_client() -> tuple:
    """获取 Embedding 客户端和模型配置"""
    cfg = _load_config().get("embedding", {})
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "text-embedding-v3")
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, cfg


MAX_RETRIES = 3
RETRY_BASE_DELAY = 1  # 秒，指数退避基数


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量文本向量化。
    自动分批（DashScope 限制 10 条/批，Ollama 无限制）。
    单批失败自动重试，全部失败才抛异常。（#2）
    """
    client, model, cfg = get_embedding_client()
    dimensions = cfg.get("dimensions")

    BATCH_SIZE = 10
    all_embeddings = []
    failed_batches = 0

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        kwargs = {"model": model, "input": batch}
        if dimensions:
            kwargs["dimensions"] = dimensions

        # 重试逻辑
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.embeddings.create(timeout=30, **kwargs)
                all_embeddings.extend(item.embedding for item in response.data)
                break
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    print(f"[Embedding] 批次 {i // BATCH_SIZE + 1} 第 {attempt} 次失败，{delay}s 后重试: {e}")
                    time.sleep(delay)
                else:
                    failed_batches += 1
                    print(f"[Embedding] 批次 {i // BATCH_SIZE + 1} 已重试 {MAX_RETRIES} 次，放弃: {e}")

    if failed_batches > 0 and len(all_embeddings) == 0:
        raise RuntimeError(f"所有 {failed_batches} 个批次均失败，无法完成向量化")

    if failed_batches > 0:
        print(f"[Embedding] 警告: {failed_batches} 个批次失败，成功向量化 {len(all_embeddings)}/{len(texts)} 条")

    return all_embeddings
