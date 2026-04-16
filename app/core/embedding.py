"""Embedding 调用 — 支持 Ollama / OpenAI 兼容接口，动态读取配置"""

import json
from pathlib import Path

from openai import OpenAI

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_embedding_client() -> tuple:
    """获取 Embedding 客户端和模型配置"""
    cfg = _load_config().get("embedding", {})
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "text-embedding-v3")
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, cfg


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量文本向量化。
    自动分批（DashScope 限制 10 条/批，Ollama 无限制）。
    """
    client, model, cfg = get_embedding_client()
    dimensions = cfg.get("dimensions")

    BATCH_SIZE = 10
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        kwargs = {"model": model, "input": batch}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = client.embeddings.create(**kwargs)
        all_embeddings.extend(item.embedding for item in response.data)
    return all_embeddings
