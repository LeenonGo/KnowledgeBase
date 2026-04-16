"""LLM 调用 — 支持 Ollama / OpenAI 兼容接口，Prompt 可配置"""

import json
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


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_prompts() -> dict:
    if PROMPTS_PATH.exists():
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
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
