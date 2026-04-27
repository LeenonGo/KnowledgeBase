"""重排模型 — 支持 qwen3-vl-rerank 等 Reranker API"""

import json
from pathlib import Path

import httpx

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"

# 配置缓存
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


def get_reranker_config() -> dict:
    """获取重排模型配置"""
    cfg = _load_config().get("reranker", {})
    return cfg


def is_reranker_enabled() -> bool:
    """重排模型是否已配置"""
    cfg = get_reranker_config()
    return bool(cfg.get("base_url") and cfg.get("model"))


def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """
    对检索结果进行重排序。

    支持 DashScope qwen3-vl-rerank 和兼容 API。
    返回按相关性降序排列的结果列表。
    """
    if not documents:
        return []

    cfg = get_reranker_config()
    base_url = cfg.get("base_url", "")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")

    if not base_url or not model:
        # 无配置，用向量余弦降级
        return _fallback_rerank(query, documents, top_k)

    # 提取文档文本
    doc_texts = [d["text"][:512] for d in documents]  # 截断避免超长

    try:
        # DashScope Reranker API 格式
        if base_url.rstrip('/').endswith('/v1'):
            url = f"{base_url.rstrip('/')}/rerank"
        else:
            url = f"{base_url.rstrip('/')}/v1/rerank"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "query": query,
            "documents": doc_texts,
            "top_n": min(top_k, len(doc_texts)),
        }

        resp = httpx.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # 解析结果
        results = data.get("results", [])
        reranked = []
        for item in results:
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0)
            if idx < len(documents):
                reranked.append({
                    **documents[idx],
                    "rerank_score": score,
                    "distance": 1.0 - score,
                })

        # 补齐未被 reranker 返回的结果
        reranked_indices = {item.get("index") for item in results}
        for i, doc in enumerate(documents):
            if i not in reranked_indices:
                reranked.append({**doc, "rerank_score": 0, "distance": 1.0})

        return reranked[:top_k]

    except Exception as e:
        print(f"[Reranker] API 调用失败，降级为余弦相似度: {e}")
        return _fallback_rerank(query, documents, top_k)


def _fallback_rerank(query: str, documents: list[dict], top_k: int) -> list[dict]:
    """降级方案：用向量余弦相似度排序"""
    from app.core.embedding import embed_texts

    if not documents:
        return documents

    query_emb = embed_texts([query])[0]
    doc_texts = [d["text"] for d in documents]
    doc_embs = embed_texts(doc_texts)

    scored = []
    for i, doc in enumerate(documents):
        sim = sum(a * b for a, b in zip(query_emb, doc_embs[i]))
        scored.append((sim, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**doc, "rerank_score": sim, "distance": 1.0 - sim} for sim, doc in scored[:top_k]]
