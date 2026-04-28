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
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=30)
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


# ─── Agent 模式 ─────────────────────────────────

def generate_answer_agent(
    question: str,
    context: str,
    history: str = "",
    tools: list = None,
    tool_context: dict = None,
) -> str:
    """
    Agent 模式问答：支持 Tool-Call 循环。
    LLM 自主决定是否调用工具，最多 5 轮工具调用。
    """
    from app.core.tools import execute_tool

    client, model, cfg = get_llm_client()
    max_tokens = cfg.get("max_tokens", 2048)
    temperature = cfg.get("temperature", 0.7)

    # Agent 模式使用专用 prompt，鼓励调用工具而非依赖上下文
    agent_system = (
        "你是一个智能知识库助手。你可以使用工具来查找信息、列出知识库、查看文档等。\n\n"
        "规则：\n"
        "1. 根据用户问题，主动调用合适的工具来获取信息\n"
        "2. 如果问题涉及知识库内容，先用 search_kb 检索\n"
        "3. 如果用户问有哪些知识库，调用 list_kb\n"
        "4. 如果需要查看完整文档，调用 get_doc_content\n"
        "5. 如果用户要求总结文档，调用 summarize_doc\n"
        "6. 工具返回的结果是你获取到的信息，必须将结果完整呈现给用户，不要说'如上所示'或'根据工具结果'，直接展示内容\n"
        "7. 回答必须标注信息来源\n"
        "8. 工具找不到相关信息时，诚实告知用户"
    )

    user_prompt = f"用户问题：{question}\n\n对话历史：{history or '无'}"

    messages = [
        {"role": "system", "content": agent_system},
        {"role": "user", "content": user_prompt},
    ]

    max_rounds = 5
    db = tool_context.get("db") if tool_context else None
    user_info = tool_context.get("user") if tool_context else None

    for round_num in range(max_rounds):
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools and db and user_info:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"[Agent] LLM 调用失败: {e}")
            return f"抱歉，AI 服务暂时不可用，请稍后重试。({e})"
        msg = response.choices[0].message

        # 没有工具调用 → 直接返回回答
        if not msg.tool_calls:
            return msg.content

        # 有工具调用 → 逐个执行
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            print(f"[Agent] Round {round_num + 1}: {func_name}({json.dumps(func_args, ensure_ascii=False)[:100]})")

            result = execute_tool(func_name, func_args, db, user_info)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:8000],  # 截断避免超长
            })

    # 超过最大轮次 → 强制最后一次无工具调用
    final_resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return final_resp.choices[0].message.content
