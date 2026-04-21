"""评测执行器 — 跑评测集，LLM-as-Judge 打分"""

import json
import time
import logging

from app.core.vectorstore import query as vector_query
from app.core.llm import generate_answer, get_llm_client

logger = logging.getLogger("kb.eval")


def _load_eval_prompts() -> dict:
    from app.core.eval_generator import _load_eval_prompts as _lep
    return _lep()


def run_single_evaluation(
    question: str,
    category: str,
    expected_answer: str,
    ref_chunks: list[str],
    kb_id: str,
    top_k: int = 5,
    use_hybrid: bool = True,
    use_reranker: bool = False,
) -> dict:
    """
    对单个问题执行完整评测流程。

    返回: {
        "retrieved_chunks": [str],
        "actual_answer": str,
        "scores": {维度: 分数},
        "reasoning": str,
        "avg_score": float,
        "passed": bool,
        "latency_ms": int,
    }
    """
    start_time = time.time()

    # 1. 检索
    try:
        results = vector_query(
            question=question,
            top_k=top_k,
            kb_id=kb_id,
            use_hybrid=use_hybrid,
            use_reranker=use_reranker,
        )
    except Exception as e:
        logger.error(f"检索失败: {e}")
        results = []

    retrieved_texts = [r["text"] for r in results]

    # 2. 生成回答
    context = "\n\n".join(retrieved_texts) if retrieved_texts else ""
    try:
        actual_answer = generate_answer(question=question, context=context, history="")
    except Exception as e:
        logger.error(f"生成回答失败: {e}")
        actual_answer = f"[生成失败: {e}]"

    gen_latency = int((time.time() - start_time) * 1000)

    # 3. LLM-as-Judge 评分
    scores, reasoning, passed = _judge_score(
        question=question,
        category=category,
        expected_answer=expected_answer,
        ref_chunks=ref_chunks,
        retrieved_chunks=retrieved_texts,
        actual_answer=actual_answer,
    )

    return {
        "retrieved_chunks": retrieved_texts,
        "actual_answer": actual_answer,
        "scores": scores,
        "reasoning": reasoning,
        "avg_score": round(sum(scores.values()) / max(len(scores), 1), 3),
        "passed": passed,
        "latency_ms": gen_latency,
    }


def _judge_score(
    question: str,
    category: str,
    expected_answer: str,
    ref_chunks: list[str],
    retrieved_chunks: list[str],
    actual_answer: str,
) -> tuple[dict, str, bool]:
    """调用 LLM 进行多维度评分"""

    prompts = _load_eval_prompts()
    judge_prompt = prompts.get("eval_judge", {})

    # 对 out_of_scope 类型特殊处理：不需要 ref_chunks
    ref_text = "\n".join(ref_chunks[:5]) if ref_chunks else "（无参考原文 — 超出知识库范围的问题）"
    retrieved_text = "\n".join(retrieved_chunks[:5]) if retrieved_chunks else "（未检索到任何内容）"

    client, model, _ = get_llm_client()

    system_prompt = judge_prompt.get("system", "")
    user_template = judge_prompt.get("user", "")

    user_prompt = user_template.format(
        question=question,
        category=category,
        expected_answer=expected_answer or "（无明确标准答案）",
        ref_chunks=ref_text,
        retrieved_chunks=retrieved_text,
        actual_answer=actual_answer,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()

        # 提取 JSON
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        result = json.loads(content)
        scores = result.get("scores", {})
        reasoning = result.get("reasoning", "")
        passed = result.get("passed", False)

        # 确保分数在 [0, 1] 范围内
        for k in scores:
            scores[k] = max(0.0, min(1.0, float(scores[k])))

        return scores, reasoning, passed

    except Exception as e:
        logger.error(f"Judge 评分失败: {e}")
        # 返回默认低分
        default_scores = {
            "retrieval_precision": 0.0,
            "retrieval_recall": 0.0,
            "retrieval_ranking": 0.0,
            "gen_groundedness": 0.0,
            "gen_relevance": 0.0,
            "gen_completeness": 0.0,
            "refuse_accuracy": 0.0,
            "currency_handling": 0.0,
            "multi_hop": 0.0,
        }
        return default_scores, f"评分失败: {e}", False
