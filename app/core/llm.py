"""LLM 调用 — 支持 Ollama / OpenAI 兼容接口，动态读取配置"""

import json
from pathlib import Path

from openai import OpenAI

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_llm_client() -> tuple:
    """获取 LLM 客户端和模型配置"""
    cfg = _load_config().get("llm", {})
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "qwen3.6-plus")
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, cfg


def generate_answer(question: str, context: str) -> str:
    """
    基于检索到的上下文生成回答。
    自动读取最新模型配置。
    """
    client, model, cfg = get_llm_client()
    max_tokens = cfg.get("max_tokens", 2048)
    temperature = cfg.get("temperature", 0.7)

    system_prompt = (
        "你是一个知识库问答助手。请根据以下参考内容回答用户的问题。\n"
        "要求：\n"
        "1. 只根据参考内容作答，不要编造信息\n"
        "2. 如果参考内容中没有相关信息，请明确告知用户\n"
        "3. 回答要简洁准确"
    )

    user_prompt = f"参考内容：\n{context}\n\n用户问题：{question}"

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
