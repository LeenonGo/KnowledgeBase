"""混合检索 — BM25 关键词检索 + RRF 融合"""

import math
import re
from collections import defaultdict

import jieba


class BM25Index:
    """内存 BM25 索引，支持中文分词"""

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0
        self.inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.documents: list[dict] = []
        self._built = False

    def _tokenize(self, text: str) -> list[str]:
        """中文分词 + 清洗"""
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = list(jieba.cut(text))
        return [w.strip() for w in words if len(w.strip()) > 1]

    def build(self, documents: list[dict]):
        """
        构建索引。
        documents: [{"id": str, "text": str, "source": str, "kb_id": str}, ...]
        """
        self.documents = documents
        self.doc_lengths = []
        self.inverted_index = defaultdict(list)

        for doc_id, doc in enumerate(documents):
            tokens = self._tokenize(doc["text"])
            self.doc_lengths.append(len(tokens))

            word_counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                word_counts[token] += 1

            for word, count in word_counts.items():
                self.inverted_index[word].append((doc_id, count))

        self.avg_doc_length = sum(self.doc_lengths) / max(len(self.doc_lengths), 1)
        self._built = True

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """BM25 检索，返回分数排序的结果"""
        if not self._built or not self.documents:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: dict[int, float] = defaultdict(float)
        n_docs = len(self.documents)

        for token in query_tokens:
            if token not in self.inverted_index:
                continue
            postings = self.inverted_index[token]
            df = len(postings)
            # IDF
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)

            for doc_id, tf in postings:
                dl = self.doc_lengths[doc_id]
                # BM25 评分
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_doc_length)
                scores[doc_id] += idf * numerator / denominator

        # 排序取 top_k
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for doc_id, score in ranked:
            doc = self.documents[doc_id]
            results.append({
                "text": doc["text"],
                "source": doc["source"],
                "distance": 1.0 / (1.0 + score),  # 转为距离（越小越好）
                "bm25_score": score,
            })
        return results


def rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """
    Reciprocal Rank Fusion — 融合向量检索和 BM25 检索的结果。

    RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
    k 通常取 60（论文推荐值）
    """
    # 用文本内容做 key 去重
    doc_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, doc in enumerate(vector_results):
        key = doc["text"][:200]  # 前 200 字符作为 key
        doc_scores[key] = doc_scores.get(key, 0) + 1.0 / (k + rank + 1)
        if key not in doc_map:
            doc_map[key] = {**doc, "rrf_vector_rank": rank + 1}

    for rank, doc in enumerate(bm25_results):
        key = doc["text"][:200]
        doc_scores[key] = doc_scores.get(key, 0) + 1.0 / (k + rank + 1)
        if key not in doc_map:
            doc_map[key] = {**doc, "rrf_bm25_rank": rank + 1}
        else:
            doc_map[key]["rrf_bm25_rank"] = rank + 1

    # 按 RRF 分数排序
    ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    results = []
    for key, rrf_score in ranked:
        doc = doc_map[key]
        results.append({
            **doc,
            "distance": 1.0 - rrf_score,  # 转为距离
            "rrf_score": rrf_score,
        })
    return results
