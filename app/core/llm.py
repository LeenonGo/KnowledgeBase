"""LLM 调用 — 读取配置，支持 OpenAI 兼容接口"""

from openai import OpenAI

from app.core.config import load_config


def get_llm_client() -> OpenAI:
    """获取 LLM 客户端"""
    config = load_config()
    llm = config.llm
    return OpenAI(base_url=llm.base_url, api_key=llm.api_key)


def generate_answer(question: str, context: str) -> str:
    """
    基于检索到的上下文生成回答。
    
    Args:
        question: 用户问题
        context: 检索到的参考文本
    Returns:
        LLM 生成的回答
    """
    config = load_config()
    llm_config = config.llm
    client = get_llm_client()

    system_prompt = (
        "你是一个知识库问答助手。请根据以下参考内容回答用户的问题。\n"
        "要求：\n"
        "1. 只根据参考内容作答，不要编造信息\n"
        "2. 如果参考内容中没有相关信息，请明确告知用户\n"
        "3. 回答要简洁准确"
    )

    user_prompt = f"参考内容：\n{context}\n\n用户问题：{question}"

    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=llm_config.max_tokens,
        temperature=llm_config.temperature,
    )

    return response.choices[0].message.content
