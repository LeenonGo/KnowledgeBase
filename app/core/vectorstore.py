"""向量存储 — 基于 Chroma，按 metadata.kb_id 隔离"""

import uuid
from pathlib import Path

import chromadb

from app.core.embedding import embed_texts

# Chroma 持久化目录
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chroma_db"

_client = chromadb.PersistentClient(path=str(DB_PATH))
_collection = _client.get_or_create_collection(
    name="knowledge_base",
    metadata={"hnsw:space": "cosine", "hnsw:ef": 200, "hnsw:M": 32},
)
# 确保 HNSW 参数正确
_meta = _collection.metadata or {}
if _meta.get("hnsw:ef") != 200 or _meta.get("hnsw:M") != 32:
    _collection.modify(metadata={"hnsw:ef": 200, "hnsw:M": 32})


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
    return len(ids)


def delete_kb_documents(kb_id: str) -> int:
    """删除某知识库下的所有文档块"""
    results = _collection.get(where={"kb_id": kb_id})
    ids = results["ids"]
    if ids:
        _collection.delete(ids=ids)
    return len(ids)


def query(question: str, top_k: int = 5, kb_id: str = None) -> list[dict]:
    """语义检索，支持按知识库过滤"""
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
    new_embedding = embed_texts([new_text])[0]
    _collection.update(ids=[chunk_id], documents=[new_text], embeddings=[new_embedding])
    return {"id": chunk_id, "char_count": len(new_text)}


def delete_chunk(chunk_id: str) -> bool:
    """删除单个分块"""
    old = _collection.get(ids=[chunk_id])
    if not old["ids"]:
        return False
    _collection.delete(ids=[chunk_id])
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
    return len(results["ids"])
