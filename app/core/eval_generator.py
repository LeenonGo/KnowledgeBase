"""评测集生成 — 从知识库文档自动构建多类型评测问题"""

import json
import random
import logging
from pathlib import Path

from openai import OpenAI

from app.core.vectorstore import _collection

logger = logging.getLogger("kb.eval")

EVAL_PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "eval_prompts.json"
_eval_prompts_cache = None
_eval_prompts_mtime = 0


def _load_eval_prompts() -> dict:
    global _eval_prompts_cache, _eval_prompts_mtime
    if EVAL_PROMPTS_PATH.exists():
        mtime = EVAL_PROMPTS_PATH.stat().st_mtime
        if _eval_prompts_cache is not None and mtime == _eval_prompts_mtime:
            return _eval_prompts_cache
        with open(EVAL_PROMPTS_PATH, "r", encoding="utf-8") as f:
            _eval_prompts_cache = json.load(f)
            _eval_prompts_mtime = mtime
        return _eval_prompts_cache
    return {}


def _get_llm_client() -> tuple:
    """复用主 LLM 配置"""
    from app.core.llm import get_llm_client
    return get_llm_client()


def _get_kb_chunks(kb_id: str, max_chunks: int = 80) -> list[str]:
    """从向量库获取知识库的所有文档块"""
    results = _collection.get(where={"kb_id": kb_id})
    if not results["documents"]:
        return []
    docs = results["documents"]
    # 随机采样，避免 prompt 过长
    if len(docs) > max_chunks:
        docs = random.sample(docs, max_chunks)
    return docs


def _distribute_questions(total: int) -> dict:
    """分配各类型问题数量"""
    # 默认分布: factual 40%, out_of_scope 20%, multi_doc 15%, ambiguous 15%, false_premise 10%
    factual = max(3, int(total * 0.4))
    oos = max(2, int(total * 0.2))
    multi = max(2, int(total * 0.15))
    amb = max(2, int(total * 0.15))
    fp = total - factual - oos - multi - amb
    if fp < 1:
        fp = 1
        # 从 factual 补
        factual = total - oos - multi - amb - fp
    return {
        "factual": factual,
        "out_of_scope": oos,
        "multi_doc": multi,
        "ambiguous": amb,
        "false_premise": fp,
    }


def generate_questions(kb_id: str, count: int = 15) -> list[dict]:
    """
    从知识库文档生成评测问题。

    返回: [{"question": str, "answer": str, "category": str, "source_hint": str, "ref_chunks": [str]}, ...]
    """
    chunks = _get_kb_chunks(kb_id)
    if not chunks:
        raise ValueError(f"知识库 {kb_id} 中没有文档内容")

    dist = _distribute_questions(count)

    # 组装文档内容（限制总长度）
    chunks_text = "\n\n---\n\n".join([f"[片段 {i+1}]\n{c}" for i, c in enumerate(chunks)])
    if len(chunks_text) > 30000:
        chunks_text = chunks_text[:30000] + "\n...（内容已截断）"

    prompts = _load_eval_prompts()
    gen_prompt = prompts.get("eval_generate", {})

    client, model, cfg = _get_llm_client()

    system_prompt = gen_prompt.get("system", "")
    user_template = gen_prompt.get("user", "")

    user_prompt = user_template.format(
        chunks=chunks_text,
        count=count,
        factual_count=dist["factual"],
        oos_count=dist["out_of_scope"],
        multi_count=dist["multi_doc"],
        amb_count=dist["ambiguous"],
        fp_count=dist["false_premise"],
    )

    logger.info(f"生成评测集: kb={kb_id}, count={count}, model={model}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        temperature=0.8,
    )

    content = response.choices[0].message.content.strip()

    # 尝试提取 JSON（兼容 markdown 代码块包裹的情况）
    if content.startswith("```"):
        lines = content.split("\n")
        # 去掉首尾 ``` 行
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        questions = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"LLM 输出 JSON 解析失败: {e}\n原始输出: {content[:500]}")
        raise ValueError(f"LLM 返回格式错误，无法解析 JSON: {e}")

    if not isinstance(questions, list):
        raise ValueError("LLM 返回结果不是数组")

    # 校验和清洗
    valid = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if "question" not in q or "category" not in q:
            continue
        q.setdefault("answer", "")
        q.setdefault("source_hint", "")
        q.setdefault("ref_chunks", [])
        if q["category"] not in ("factual", "out_of_scope", "multi_doc", "ambiguous", "false_premise"):
            q["category"] = "factual"
        valid.append(q)

    logger.info(f"生成完成: {len(valid)} 个有效问题")
    return valid
