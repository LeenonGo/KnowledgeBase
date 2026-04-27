"""LLM 调用 — 支持 Ollama / OpenAI 兼容接口，Prompt 可配置"""

import json
import re
from pathlib import Path

from openai import OpenAI

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"
PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "prompts.json"

# 兜底默认 Prompt
DEFAULT_PROMPTS = {
    "qa": {
        "system": "你是一个知识库问答助手。请根据以下参考内容回答用户的问题。\n要求：\n1. 只根据参考内容作答，不要编造信息\n2. 如果参考内容中没有相关信息，请明确告知用户\n3. 回答要简洁准确",
        "user": "参考内容：\n{context}\n\n用户问题：{question}",
    },
    "rewrite": {
        "system": "你是一个查询改写助手。将用户的问题改写为独立完整的查询。只输出改写结果。",
        "user": "对话历史：\n{history}\n\n当前问题：{question}\n\n改写：",
    },
    "refuse": {
        "answer": "抱歉，我在当前知识库中未找到与您问题相关的信息。",
    },
}

# ─── 配置缓存（#5） ─────────────────────────────
_config_cache = None
_config_mtime = 0
_prompts_cache = None
_prompts_mtime = 0


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


def _load_prompts() -> dict:
    global _prompts_cache, _prompts_mtime
    if PROMPTS_PATH.exists():
        mtime = PROMPTS_PATH.stat().st_mtime
        if _prompts_cache is not None and mtime == _prompts_mtime:
            return _prompts_cache
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            _prompts_cache = json.load(f)
            _prompts_mtime = mtime
        return _prompts_cache
    return DEFAULT_PROMPTS


def get_prompt(prompt_type: str = "qa") -> dict:
    """获取指定类型的 Prompt 模板"""
    prompts = _load_prompts()
    return prompts.get(prompt_type, DEFAULT_PROMPTS.get(prompt_type, {}))


def get_llm_client() -> tuple:
    """获取 LLM 客户端和模型配置"""
    cfg = _load_config().get("llm", {})
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "qwen3.6-plus")
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, cfg


def generate_answer(question: str, context: str, history: str = "") -> str:
    """
    基于检索到的上下文生成回答。
    自动读取最新模型配置和 Prompt 模板。
    """
    client, model, cfg = get_llm_client()
    max_tokens = cfg.get("max_tokens", 2048)
    temperature = cfg.get("temperature", 0.7)

    prompt = get_prompt("qa")
    system_prompt = prompt.get("system", DEFAULT_PROMPTS["qa"]["system"])
    user_template = prompt.get("user", DEFAULT_PROMPTS["qa"]["user"])

    user_prompt = user_template.format(
        context=context,
        question=question,
        history=history or "无",
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content


def rewrite_query(question: str, history: str = "") -> str:
    """
    多轮对话中，将带指代的问题改写为独立完整的查询。
    """
    client, model, cfg = get_llm_client()

    prompt = get_prompt("rewrite")
    system_prompt = prompt.get("system", DEFAULT_PROMPTS["rewrite"]["system"])
    user_template = prompt.get("user", DEFAULT_PROMPTS["rewrite"]["user"])

    user_prompt = user_template.format(
        history=history or "无",
        question=question,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=256,
        temperature=0.3,
    )

    return response.choices[0].message.content


def get_refuse_answer() -> str:
    """获取拒答话术"""
    prompt = get_prompt("refuse")
    return prompt.get("answer", DEFAULT_PROMPTS["refuse"]["answer"])


def polish_query(question: str) -> dict:
    """
    润色查询：拼写纠错 + 同义扩展 + 关键词提取。
    返回 {"corrected": str, "expanded": str, "keywords": list[str]}
    失败时返回原始问题，不影响正常流程。
    """
    import json as _json
    try:
        client, model, cfg = get_llm_client()

        prompt = get_prompt("polish")
        system_prompt = prompt.get("system", "")
        user_template = prompt.get("user", "用户查询：{question}\n\n请输出优化结果 JSON：")

        user_prompt = user_template.format(question=question)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=256,
            temperature=0.3,
        )

        raw = response.choices[0].message.content.strip()
        # 提取 JSON（兼容 markdown 代码块包裹）
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        result = _json.loads(raw)

        return {
            "corrected": result.get("corrected", question),
            "expanded": result.get("expanded", question),
            "keywords": result.get("keywords", []),
        }
    except Exception as e:
        print(f"[QueryPolish] 润色失败，降级到原始查询: {e}")
        return {"corrected": question, "expanded": question, "keywords": []}
