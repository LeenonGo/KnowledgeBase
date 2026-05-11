"""LLM 调用 — 支持 Ollama / OpenAI 兼容接口，Prompt 可配置"""

import json
import re

from openai import OpenAI

from app.core.config import get_llm_config, load_prompts_config

# 兜底默认 Prompt
DEFAULT_PROMPTS = {
    "qa": {
        "system": "你是一个知识库问答助手。请根据以下参考内容回答用户的问题。\n要求：\n1. 只根据参考内容作答，不要编造信息\n2. 如果参考内容中没有相关信息，请明确告知用户\n3. 回答要简洁准确\n4. 引用参考内容时使用 [C编号] 标注来源，例如 [C1] [C2]。每个关键事实后面都要标注对应的引用编号",
        "user": "参考内容（每段已编号）：\n{context}\n\n用户问题：{question}",
    },
    "rewrite": {
        "system": "你是一个查询改写助手。将用户的问题改写为独立完整的查询。只输出改写结果。",
        "user": "对话历史：\n{history}\n\n当前问题：{question}\n\n改写：",
    },
    "refuse": {
        "answer": "抱歉，我在当前知识库中未找到与您问题相关的信息。",
    },
}

def get_prompt(prompt_type: str = "qa") -> dict:
    """获取指定类型的 Prompt 模板"""
    prompts = load_prompts_config()
    return prompts.get(prompt_type, DEFAULT_PROMPTS.get(prompt_type, {}))


def get_llm_client() -> tuple:
    """获取 LLM 客户端和模型配置"""
    cfg = get_llm_config()
    base_url = cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "qwen3.6-plus")
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=30)
    return client, model, cfg


def generate_answer(question: str, context: str, history: str = "") -> str:
    """
    基于检索到的上下文生成回答（完整返回）。
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


def generate_answer_stream(question: str, context: str, history: str = ""):
    """
    基于检索到的上下文流式生成回答。
    返回一个生成器，每次 yield 一个 token。
    同时检查 [来源:xxx] 模式，yield 元事件标注 source 列表。
    """
    import re

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

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )

    buffer = ""
    source_pattern = re.compile(r'\[来源:\s*([^\]]+)\]')
    extracted_sources = set()

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue

        buffer += delta

        # 边接收边检测 [来源:xxx] 模式
        for match in source_pattern.finditer(buffer):
            src = match.group(1).strip()
            if src and src not in extracted_sources:
                extracted_sources.add(src)
                yield {"type": "source", "source": src}

        yield {"type": "token", "content": delta}

    # 流结束后把 buffer 里残留的 [来源:xxx] 也提取完（可能在最后一个 chunk）
    for match in source_pattern.finditer(buffer):
        src = match.group(1).strip()
        if src and src not in extracted_sources:
            extracted_sources.add(src)
            yield {"type": "source", "source": src}

    yield {"type": "done"}


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


def parse_citations(answer: str, citation_map: dict[str, dict] = None) -> tuple[str, list[dict]]:
    """
    解析回答中的 [C1][C2] 引用标记，替换为 [1][2] 序号，构建 citations 数组。

    Args:
        answer: LLM 原始回答，包含 [C1] [C2] 等标记
        citation_map: {"C1": {"citation_id": ..., "source": ..., "text_preview": ...}, ...}

    Returns:
        (替换后的回答, citations 数组)
    """
    if not answer:
        return answer, []

    # 找出所有 [C数字] 引用
    cite_pattern = re.compile(r'\[C(\d+)\]')
    found_cites = cite_pattern.findall(answer)
    # 去重并保持顺序
    seen = set()
    unique_refs = []  # [("C1", 1), ("C2", 2), ...]
    for ref in found_cites:
        key = f"C{ref}"
        if key not in seen:
            seen.add(key)
            unique_refs.append((key, len(unique_refs) + 1))

    # 构建映射 C1 -> [1] 序号
    cite_to_num = {key: num for key, num in unique_refs}

    # 替换 [C1] -> [1]
    def _replace(match):
        key = f"C{match.group(1)}"
        num = cite_to_num.get(key)
        if num is not None:
            return f'[{num}]'
        return match.group(0)

    new_answer = cite_pattern.sub(_replace, answer)

    # 构建 citations 数组
    citations = []
    for key, num in unique_refs:
        info = (citation_map or {}).get(key, {})
        citations.append({
            "index": num,
            "citation_id": info.get("citation_id", ""),
            "source": info.get("source", ""),
            "text_preview": info.get("text_preview", ""),
        })

    return new_answer, citations


def format_context_with_citations(docs: list[dict]) -> tuple[str, dict[str, dict]]:
    """
    将检索结果格式化为带 [C编号] 的上下文，同时构建引用映射。

    Args:
        docs: 检索结果列表，需包含 text, source, citation_id 字段

    Returns:
        (格式化的上下文字符串, citation_map)
    """
    parts = []
    citation_map = {}
    for i, d in enumerate(docs, 1):
        key = f"C{i}"
        part = f'[C{i} 来源: {d["source"]}]\n{d["text"]}'

        parts.append(part)
        citation_map[key] = {
            "citation_id": d.get("citation_id", ""),
            "source": d.get("source", ""),
            "text_preview": d["text"][:200],
        }
    return "\n\n".join(parts), citation_map


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


def generate_answer_agent_stream(
    question: str,
    context: str,
    history: str = "",
    tools: list = None,
    tool_context: dict = None,
):
    """
    Agent 模式问答流式版本 — yield 结构化事件用于推理链可视化。
    事件类型: thought / action / observe / answer / error
    """
    from app.core.tools import execute_tool

    client, model, cfg = get_llm_client()
    max_tokens = cfg.get("max_tokens", 2048)
    temperature = cfg.get("temperature", 0.7)

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
        # 生成思考步骤
        yield {"type": "thought", "step": round_num + 1,
               "content": f"分析问题，决定第 {round_num + 1} 步操作..."}

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
            yield {"type": "error", "content": f"LLM 调用失败: {e}"}
            return

        msg = response.choices[0].message

        # 没有工具调用 → 直接返回回答
        if not msg.tool_calls:
            yield {"type": "thought", "step": round_num + 1,
                   "content": msg.content[:200] if msg.content else "准备回答"}
            yield {"type": "answer", "content": msg.content or "", "sources": []}
            return

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

            # 发送 action 事件
            yield {"type": "action", "step": round_num + 1,
                   "tool": func_name, "arguments": func_args}

            result = execute_tool(func_name, func_args, db, user_info)

            # 发送 observe 事件
            yield {"type": "observe", "step": round_num + 1,
                   "content": result[:500]}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:8000],
            })

    # 超过最大轮次 → 强制最后一次无工具调用
    final_resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    yield {"type": "answer", "content": final_resp.choices[0].message.content, "sources": []}
