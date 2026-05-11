"""向量存储 — ChromaDB + BM25 混合检索 + RRF 融合"""

import uuid
from pathlib import Path

import chromadb

from app.core.embedding import embed_texts

# Chroma 持久化目录
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chroma_db"

_client = chromadb.PersistentClient(path=str(DB_PATH))
_collection = _client.get_or_create_collection(
    name="knowledge_base",
    metadata={"hnsw:space": "cosine", "hnsw:ef": 500, "hnsw:M": 32},
)
_meta = _collection.metadata or {}
if _meta.get("hnsw:ef") != 500 or _meta.get("hnsw:M") != 32:
    _collection.modify(metadata={"hnsw:ef": 500, "hnsw:M": 32})

# ─── BM25 索引缓存（按 kb_id 隔离，线程安全）──
import threading as _threading
from app.core.hybrid_search import BM25Index, rrf_fusion

# 每个 kb_id 独立索引，避免全量扫描
_bm25_indexes: dict[str, BM25Index] = {}  # kb_id -> BM25Index
_bm25_doc_counts: dict[str, int] = {}      # kb_id -> doc_count
_bm25_dirty: set[str] = set()               # 脏的 kb_id 集合
_bm25_lock = _threading.Lock()

# BM25 索引最大文档数限制（防内存爆炸）
_BM25_MAX_DOCS = 50000


def _get_bm25_index(kb_id: str = None) -> BM25Index:
    """获取 BM25 索引（懒构建，按 kb_id 隔离，线程安全）"""
    key = kb_id or "__all__"

    with _bm25_lock:
        if key in _bm25_indexes and key not in _bm25_dirty:
            return _bm25_indexes[key]

    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()
    current_count = len(results["ids"])

    with _bm25_lock:
        # double-check
        if (key in _bm25_indexes and key not in _bm25_dirty
                and _bm25_doc_counts.get(key) == current_count):
            return _bm25_indexes[key]

        docs = []
        for i in range(len(results["ids"])):
            if i >= _BM25_MAX_DOCS:
                print(f"[BM25] KB={key} 文档数({current_count})超过上限{_BM25_MAX_DOCS}")
                break
            meta = results["metadatas"][i] if results["metadatas"] else {}
            docs.append({
                "text": results["documents"][i],
                "source": meta.get("source", ""),
                "kb_id": meta.get("kb_id", ""),
            })
        idx = BM25Index()
        idx.build(docs)
        _bm25_indexes[key] = idx
        _bm25_doc_counts[key] = current_count
        _bm25_dirty.discard(key)
        return idx


def _mark_dirty(kb_id: str = None):
    """标记指定 kb 的 BM25 索引需要重建"""
    with _bm25_lock:
        key = kb_id or "__all__"
        _bm25_dirty.add(key)
        if kb_id:
            _bm25_dirty.add("__all__")


def add_documents(chunks: list[str], filename: str, kb_id: str = "default") -> int:
    """将文本块写入向量库，关联到指定知识库"""
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": filename, "kb_id": kb_id} for _ in chunks]

    _collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    _mark_dirty(kb_id)
    return len(chunks)


def list_documents(kb_id: str = None) -> list[dict]:
    """列出已入库的文档及其块数"""
    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()

    source_count: dict[str, int] = {}
    for meta in results["metadatas"]:
        src = meta["source"]
        source_count[src] = source_count.get(src, 0) + 1
    return [{"filename": name, "chunks": count} for name, count in source_count.items()]


def get_all_kb_stats() -> dict[str, dict]:
    """一次查询返回所有知识库的文档数和分块数"""
    results = _collection.get()
    stats: dict[str, dict] = {}
    for meta in results["metadatas"]:
        kb_id = meta.get("kb_id", "default")
        src = meta.get("source", "")
        if kb_id not in stats:
            stats[kb_id] = {"docs": set(), "chunks": 0}
        stats[kb_id]["docs"].add(src)
        stats[kb_id]["chunks"] += 1
    return {k: {"doc_count": len(v["docs"]), "chunk_count": v["chunks"]} for k, v in stats.items()}


def delete_document(filename: str, kb_id: str = None) -> int:
    """按来源文件名删除所有相关块"""
    if kb_id:
        results = _collection.get(where={"$and": [{"source": filename}, {"kb_id": kb_id}]})
    else:
        results = _collection.get(where={"source": filename})

    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
        _mark_dirty(kb_id)
    return len(ids)


def delete_kb_documents(kb_id: str) -> int:
    """删除某知识库下的所有文档块"""
    results = _collection.get(where={"kb_id": kb_id})
    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
        _mark_dirty(kb_id)
    return len(ids)


def query(
    question: str,
    top_k: int = 5,
    kb_id: str = None,
    use_hybrid: bool = True,
    use_reranker: bool = False,
    keywords: list[str] = None,
) -> list[dict]:
    """
    语义检索，支持混合检索（向量 + BM25 + RRF）。
    """
    embedding = embed_texts([question])[0]

    # 向量检索（n_results 不能超过文档总数）
    if kb_id:
        count_results = _collection.get(where={"kb_id": kb_id})
        total_docs = len(count_results["ids"])
    else:
        total_docs = _collection.count()
    vec_n = min(max(top_k * 2, 10), total_docs) if total_docs > 0 else top_k

    vec_kwargs = {
        "query_embeddings": [embedding],
        "n_results": vec_n,
    }
    if kb_id:
        vec_kwargs["where"] = {"kb_id": kb_id}

    try:
        vec_results_raw = _collection.query(**vec_kwargs)
    except Exception as e:
        print(f"[VectorStore] 向量检索失败: {e}")
        vec_results_raw = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    # 获取向量库 ID 列表（用于引用标注）
    vec_ids = vec_results_raw.get("ids", [[]])[0] if vec_results_raw.get("ids") else []

    vector_results = []
    if vec_results_raw["documents"] and vec_results_raw["documents"][0]:
        for i in range(len(vec_results_raw["documents"][0])):
            meta = vec_results_raw["metadatas"][0][i] if vec_results_raw["metadatas"] else {}
            result = {
                "text": vec_results_raw["documents"][0][i],
                "source": meta.get("source", ""),
                "distance": vec_results_raw["distances"][0][i],
                "vectorstore_id": vec_ids[i] if i < len(vec_ids) else "",
                "kb_id": meta.get("kb_id", ""),
            }
            vector_results.append(result)

    if not use_hybrid:
        return vector_results[:top_k]

    # BM25 检索 — 拼接 keywords 提升关键词命中率
    bm25_idx = _get_bm25_index(kb_id)
    bm25_text = question
    if keywords:
        bm25_text = question + " " + " ".join(keywords)
    bm25_results = bm25_idx.search(bm25_text, top_k=top_k * 2)

    # RRF 融合
    fused = rrf_fusion(vector_results, bm25_results, k=60, top_k=top_k)

    # 精排（可选）
    if use_reranker:
        from app.core.reranker import rerank as rerank_fn
        fused = rerank_fn(question, fused, top_k)

    return fused



def get_chunks(filename: str, kb_id: str = None) -> list[dict]:
    """获取文档的所有分块"""
    if kb_id:
        results = _collection.get(where={"$and": [{"source": filename}, {"kb_id": kb_id}]})
    else:
        results = _collection.get(where={"source": filename})

    chunks = []
    for i in range(len(results["ids"])):
        meta = results["metadatas"][i] if results["metadatas"] else {}
        chunks.append({
            "id": results["ids"][i], "index": i + 1,
            "text": results["documents"][i],
            "char_count": len(results["documents"][i]),
            "source": meta.get("source", filename),
            "kb_id": meta.get("kb_id", ""),
        })
    return chunks


def update_chunk(chunk_id: str, new_text: str) -> dict:
    """更新单个分块内容"""
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        raise ValueError("分块不存在")
    kb_id = (old["metadatas"] or [{}])[0].get("kb_id")
    new_embedding = embed_texts([new_text])[0]
    _collection.update(ids=[chunk_id], documents=[new_text], embeddings=[new_embedding])
    _mark_dirty(kb_id)
    return {"id": chunk_id, "char_count": len(new_text)}


def delete_chunk(chunk_id: str) -> bool:
    """删除单个分块"""
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        return False
    kb_id = (old["metadatas"] or [{}])[0].get("kb_id")
    _collection.delete(ids=[chunk_id])
    _mark_dirty(kb_id)
    return True


def reindex_kb(kb_id: str = None) -> int:
    """重建指定知识库（或全部）的向量索引"""
    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()

    if not results["ids"]:
        return 0

    new_embeddings = embed_texts(results["documents"])
    _collection.update(ids=results["ids"], embeddings=new_embeddings)
    _mark_dirty(kb_id)
    return len(results["ids"])


def search_accessible(
    question: str,
    top_k: int = 5,
    kb_id: str = None,
    accessible_ids: list[str] | None = None,
    use_hybrid: bool = True,
    use_reranker: bool = False,
    keywords: list[str] = None,
) -> list[dict]:
    """
    统一搜索入口 — 自动处理权限过滤。

    Args:
        question: 查询文本
        top_k: 返回数量
        kb_id: 指定知识库（为 None 则搜索所有可访问的）
        accessible_ids: 用户可访问的 KB 列表（None=全部，[]=无）
        use_hybrid: 是否混合检索
        use_reranker: 是否重排
        keywords: 润色关键词
    Returns:
        检索结果列表
    """
    if kb_id:
        results = query(question, top_k=top_k, kb_id=kb_id,
                     use_hybrid=use_hybrid, use_reranker=use_reranker,
                     keywords=keywords)
        return _attach_citation_meta(results)

    if accessible_ids is None:
        # super_admin，搜索全部
        results = query(question, top_k=top_k, use_hybrid=use_hybrid,
                     use_reranker=use_reranker, keywords=keywords)
        return _attach_citation_meta(results)

    if not accessible_ids:
        return []

    # 遍历所有可访问 KB，合并排序
    all_docs = []
    for kid in accessible_ids:
        all_docs.extend(query(question, top_k=top_k, kb_id=kid,
                              use_hybrid=use_hybrid, use_reranker=use_reranker,
                              keywords=keywords))
    all_docs.sort(key=lambda x: x.get("distance", 0))
    return _attach_citation_meta(all_docs[:top_k])


def _attach_citation_meta(docs: list[dict]) -> list[dict]:
    """为检索结果附加引用元数据（citation_id, chunk_index）"""
    for i, doc in enumerate(docs):
        kid = doc.get("kb_id", "default")
        vid = doc.get("vectorstore_id", "")
        doc["citation_id"] = f"cite_{kid}_{vid[:8]}" if vid else f"cite_{kid}_{i}"
        doc["chunk_index"] = i + 1
    return docs
