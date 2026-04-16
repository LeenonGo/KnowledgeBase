"""Embedding 调用 — 读取配置，支持 OpenAI 兼容接口"""

from openai import OpenAI

from app.core.config import load_config


def get_embedding_client() -> OpenAI:
    """获取 Embedding 客户端"""
    config = load_config()
    emb = config.embedding
    return OpenAI(base_url=emb.base_url, api_key=emb.api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量文本向量化。
    
    Args:
        texts: 待向量化的文本列表
    Returns:
        向量列表
    """
    config = load_config()
    emb = config.embedding
    client = get_embedding_client()

    # DashScope 限制每批最多 10 条，分批处理
    BATCH_SIZE = 10
    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(
            model=emb.model,
            input=batch,
            dimensions=emb.dimensions,
        )
        all_embeddings.extend(item.embedding for item in response.data)
    return all_embeddings
