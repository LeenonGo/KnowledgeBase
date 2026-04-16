"""向量存储 — 基于 Chroma，支持按知识库隔离"""

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


def add_documents(chunks: list[str], filename: str, kb_id: str = "default") -> int:
    """
    将文本块写入向量库，关联到指定知识库。

    Args:
        chunks: 分块后的文本列表
        filename: 来源文件名
        kb_id: 知识库 ID
    Returns:
        写入的文档数量
    """
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

    return len(chunks)


def list_documents(kb_id: str = None) -> list[dict]:
    """
    列出已入库的文档及其块数。

    Args:
        kb_id: 知识库 ID，为 None 时列出所有
    """
    if kb_id:
        results = _collection.get(where={"kb_id": kb_id})
    else:
        results = _collection.get()

    source_count: dict[str, int] = {}
    for meta in results["metadatas"]:
        src = meta["source"]
        source_count[src] = source_count.get(src, 0) + 1
    return [{"filename": name, "chunks": count} for name, count in source_count.items()]


def delete_document(filename: str, kb_id: str = None) -> int:
    """
    按来源文件名删除所有相关块。

    Args:
        filename: 文件名
        kb_id: 知识库 ID，指定时只删该知识库下的
    """
    if kb_id:
        results = _collection.get(where={"$and": [{"source": filename}, {"kb_id": kb_id}]})
    else:
        results = _collection.get(where={"source": filename})

    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
    return len(ids)


def delete_kb_documents(kb_id: str) -> int:
    """删除某知识库下的所有文档块"""
    results = _collection.get(where={"kb_id": kb_id})
    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
    return len(ids)


def query(question: str, top_k: int = 5, kb_id: str = None) -> list[dict]:
    """
    语义检索，支持按知识库过滤。

    Args:
        question: 用户问题
        top_k: 返回最相似的 top_k 条
        kb_id: 知识库 ID，指定时只在该知识库内检索
    Returns:
        包含 text、source、distance 的结果列表
    """
    embedding = embed_texts([question])[0]

    kwargs = {
        "query_embeddings": [embedding],
        "n_results": top_k,
    }
    if kb_id:
        kwargs["where"] = {"kb_id": kb_id}

    results = _collection.query(**kwargs)

    docs = []
    for i in range(len(results["documents"][0])):
        docs.append({
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "distance": results["distances"][0][i],
        })

    return docs
