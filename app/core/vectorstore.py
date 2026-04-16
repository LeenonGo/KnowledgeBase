"""向量存储 — 基于 Chroma"""

import uuid
from pathlib import Path

import chromadb

from app.core.embedding import embed_texts

# Chroma 持久化目录
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chroma_db"

_client = chromadb.PersistentClient(path=str(DB_PATH))
_collection = _client.get_or_create_collection(
    name="knowledge_base",
    metadata={"hnsw:space": "cosine"},
)


def add_documents(chunks: list[str], filename: str) -> int:
    """
    将文本块写入向量库。
    
    Args:
        chunks: 分块后的文本列表
        filename: 来源文件名
    Returns:
        写入的文档数量
    """
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": filename} for _ in chunks]

    _collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return len(chunks)


def list_documents() -> list[dict]:
    """列出已入库的文档及其块数"""
    results = _collection.get()
    source_count: dict[str, int] = {}
    for meta in results["metadatas"]:
        src = meta["source"]
        source_count[src] = source_count.get(src, 0) + 1
    return [{"filename": name, "chunks": count} for name, count in source_count.items()]


def delete_document(filename: str) -> int:
    """按来源文件名删除所有相关块，返回删除数量"""
    results = _collection.get(where={"source": filename})
    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
    return len(ids)


def query(question: str, top_k: int = 5) -> list[dict]:
    """
    语义检索。
    
    Args:
        question: 用户问题
        top_k: 返回最相似的 top_k 条
    Returns:
        包含 text、source、distance 的结果列表
    """
    embedding = embed_texts([question])[0]

    results = _collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
    )

    docs = []
    for i in range(len(results["documents"][0])):
        docs.append({
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "distance": results["distances"][0][i],
        })

    return docs
