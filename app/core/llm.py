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


def _trim_messages(msgs):
    """控制上下文长度，防止超出模型窗口。保留 system + user prompt + 最近工具调用。"""
    total = sum(len(str(m.get("content", ""))) for m in msgs)
    cfg = get_llm_config()
    # 从配置读取上下文上限，默认 60000 字符
    max_chars = cfg.get("agent_max_context_chars", 60000)
    while total > max_chars and len(msgs) > 4:
        # 跳过 system(0) 和 user prompt(1)，从最早的工具轮次开始删
        removed = msgs.pop(2)
        total -= len(str(removed.get("content", "")))
    return msgs


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
    temperature = cfg.get("temperature", 0.7)
    # Agent 需要更长的输出，独立于全局 max_tokens
    max_tokens = 4096

    # Agent 模式使用专用 prompt，鼓励调用工具而非依赖上下文
    agent_prompt = get_prompt("agent")
    agent_system = agent_prompt.get("system", "你是一个智能知识库助手，请使用工具来回答问题。")

    user_prompt = f"用户问题：{question}\n\n对话历史：{history or '无'}"

    messages = [
        {"role": "system", "content": agent_system},
        {"role": "user", "content": user_prompt},
    ]

    max_rounds = 7
    db = tool_context.get("db") if tool_context else None
    user_info = tool_context.get("user") if tool_context else None
    collected_sources = []  # 收集工具返回的来源信息

    for round_num in range(max_rounds):
        # 控制上下文长度
        messages = _trim_messages(messages)

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
    messages = _trim_messages(messages)
    messages.append({"role": "user", "content": "请基于以上所有工具返回的信息，直接给出完整详细的回答。不要调用工具。"})
    final_resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        # 不传 tools，强制直接回答
    )
    return final_resp.choices[0].message.content or "（Agent 已完成信息收集，但未能生成回答，请尝试换一种问法）"


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
    temperature = cfg.get("temperature", 0.7)
    # Agent 需要更长的输出，独立于全局 max_tokens
    max_tokens = 4096

    agent_prompt = get_prompt("agent")
    agent_system = agent_prompt.get("system", "你是一个智能知识库助手，请使用工具来回答问题。")

    user_prompt = f"用户问题：{question}\n\n对话历史：{history or '无'}"

    messages = [
        {"role": "system", "content": agent_system},
        {"role": "user", "content": user_prompt},
    ]

    max_rounds = 7
    db = tool_context.get("db") if tool_context else None
    user_info = tool_context.get("user") if tool_context else None
    collected_sources = []  # 收集工具返回的来源
    collected_citation_map = {}  # 引用映射 C1 -> {source, text_preview}

    for round_num in range(max_rounds):
        # 生成思考步骤（占位）
        _label = '开始分析问题' if round_num == 0 else f'继续第 {round_num + 1} 步操作'
        yield {"type": "thought", "step": round_num + 1, "content": f"{_label}..."}

        # 控制上下文长度
        messages = _trim_messages(messages)

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
            yield {"type": "answer", "content": msg.content or "", "sources": collected_sources}
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

            # 从工具结果中提取来源和引用信息
            for _src in re.findall(r'来源:([^\]\n]+)', result):
                _src = _src.strip().rstrip(']')
                if _src and _src not in collected_sources:
                    collected_sources.append(_src)
            # 解析 [C数字 来源:xxx] 格式，构建引用映射
            for _m in re.finditer(r'\[C(\d+) 来源:([^\] ]+)[^\]]*\]\n(.{0,200})', result):
                _key = f"C{_m.group(1)}"
                if _key not in collected_citation_map:
                    collected_citation_map[_key] = {
                        "source": _m.group(2).strip(),
                        "text_preview": _m.group(3).strip(),
                    }

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:8000],
            })

    # 超过最大轮次 → 强制最后一次无工具调用
    messages = _trim_messages(messages)
    messages.append({"role": "user", "content": "请基于以上所有工具返回的信息，直接给出完整详细的回答。不要调用工具。"})
    final_resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        # 不传 tools，强制直接回答
    )
    _final_answer = final_resp.choices[0].message.content or "（Agent 已完成信息收集，但未能生成回答，请尝试换一种问法）"

    # 提取工具结果中的图表标记，确保保留在最终回答中
    _all_tool_text = '\n'.join(str(m.get('content', '')) for m in messages if m.get('role') == 'tool')
    _charts = re.findall(r'\[CHART\].*?\[/CHART\]', _all_tool_text, re.DOTALL)
    if _charts and '[CHART]' not in _final_answer:
        _final_answer += '\n\n' + '\n\n'.join(_charts)

    yield {"type": "answer", "content": _final_answer, "sources": collected_sources}


def plan_and_execute_stream(
    question: str,
    context: str,
    history: str = "",
    tools: list = None,
    tool_context: dict = None,
):
    """
    Plan-and-Execute 模式流式问答。
    Phase 1: Planning — 分析问题复杂度，拆解子任务
    Phase 2: Execute — 每个子任务独立 ReAct 循环
    Phase 3: Synthesize — 综合所有结果生成最终回答
    """
    from app.core.tools import execute_tool

    client, model, cfg = get_llm_client()
    temperature = cfg.get("temperature", 0.7)
    max_tokens = 4096

    db = tool_context.get("db") if tool_context else None
    user_info = tool_context.get("user") if tool_context else None

    # ═══════════════════════════════════════════════════════
    # Phase 1: Planning
    # ═══════════════════════════════════════════════════════
    planner_prompt = get_prompt("planner")
    planner_system = planner_prompt.get("system", "判断问题复杂度，输出 JSON。")
    planner_user = planner_prompt.get("user", "问题：{question}").format(question=question)

    try:
        plan_resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": planner_system},
                {"role": "user", "content": planner_user},
            ],
            max_tokens=512,
            temperature=0.1,  # 低温度，稳定输出
        )
        plan_raw = plan_resp.choices[0].message.content or ""
        # 提取 JSON（兼容 markdown code block 包裹）
        json_match = re.search(r'\{.*\}', plan_raw, re.DOTALL)
        plan_data = json.loads(json_match.group()) if json_match else {"need_plan": False}
    except Exception as e:
        print(f"[Plan] 规划失败，降级为直接执行: {e}")
        plan_data = {"need_plan": False}

    need_plan = plan_data.get("need_plan", False)
    tasks = plan_data.get("tasks", [])
    reason = plan_data.get("reason", "")

    # 输出规划事件
    yield {
        "type": "plan",
        "need_plan": need_plan,
        "reason": reason,
        "tasks": [{"id": t.get("id", i+1), "description": t.get("description", "")}
                   for i, t in enumerate(tasks)],
    }

    # 简单问题 → 降级为普通 Agent 流
    if not need_plan or len(tasks) < 2:
        yield {"type": "thought", "step": 1, "content": "问题较简单，直接执行检索问答..."}
        yield from generate_answer_agent_stream(question, context, history, tools, tool_context)
        return

    # ═══════════════════════════════════════════════════════
    # Phase 2: Execute each sub-task
    # ═══════════════════════════════════════════════════════
    all_results = []  # [{task_id, description, result, sources}]
    all_sources = set()
    global_step = 0

    for task in tasks:
        task_id = task.get("id", len(all_results) + 1)
        task_desc = task.get("description", "")
        search_hint = task.get("search_hint", "")

        yield {"type": "subtask_start", "task_id": task_id, "description": task_desc}

        # 每个子任务独立 ReAct 循环（最多 3 轮）
        sub_messages = [
            {"role": "system", "content": (
                "你是一个知识库检索助手。请使用工具来完成以下子任务。\n"
                "完成后给出简洁的结果总结。"
            )},
            {"role": "user", "content": f"子任务：{task_desc}\n检索提示：{search_hint}"},
        ]
        sub_result = ""
        sub_max_rounds = 3

        for sub_round in range(sub_max_rounds):
            global_step += 1
            yield {"type": "thought", "step": global_step,
                   "content": f"[子任务{task_id}] {'开始执行' if sub_round == 0 else f'继续第 {sub_round+1} 步'}"}

            sub_messages = _trim_messages(sub_messages)
            kwargs = {
                "model": model,
                "messages": sub_messages,
                "max_tokens": 1024,
                "temperature": temperature,
            }
            if tools and db and user_info:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception as e:
                yield {"type": "error", "content": f"子任务{task_id} LLM调用失败: {e}"}
                break

            msg = resp.choices[0].message

            # 没有工具调用 → 子任务完成
            if not msg.tool_calls:
                sub_result = msg.content or ""
                yield {"type": "thought", "step": global_step,
                       "content": f"[子任务{task_id}] 完成"}
                break

            # 有工具调用
            sub_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                global_step += 1
                yield {"type": "action", "step": global_step,
                       "tool": func_name, "arguments": func_args}

                result = execute_tool(func_name, func_args, db, user_info)

                yield {"type": "observe", "step": global_step,
                       "content": result[:500]}

                # 收集来源
                for _src in re.findall(r'来源:([^\]\n]+)', result):
                    _src = _src.strip().rstrip(']')
                    if _src:
                        all_sources.add(_src)

                sub_messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": result[:8000],
                })
        else:
            # 超过轮次，强制总结
            sub_messages.append({"role": "user", "content": "请直接总结以上信息。"})
            try:
                final = client.chat.completions.create(
                    model=model, messages=sub_messages, max_tokens=1024, temperature=temperature)
                sub_result = final.choices[0].message.content or ""
            except Exception:
                sub_result = "（子任务执行超时）"

        all_results.append({
            "task_id": task_id,
            "description": task_desc,
            "result": sub_result,
        })
        yield {"type": "subtask_done", "task_id": task_id,
               "result_preview": sub_result[:200]}

    # ═══════════════════════════════════════════════════════
    # Phase 3: Synthesize
    # ═══════════════════════════════════════════════════════
    synth_prompt = get_prompt("synthesizer")
    synth_system = synth_prompt.get("system", "综合子任务结果生成回答。")

    results_text = "\n\n".join(
        f"### 子任务 {r['task_id']}: {r['description']}\n{r['result']}"
        for r in all_results
    )
    synth_user = synth_prompt.get("user", "问题：{question}\n结果：{results}").format(
        question=question, results=results_text)

    global_step += 1
    yield {"type": "thought", "step": global_step, "content": "综合所有子任务结果，生成最终回答..."}

    try:
        synth_resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": synth_system},
                {"role": "user", "content": synth_user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        final_answer = synth_resp.choices[0].message.content or ""
    except Exception as e:
        final_answer = f"综合生成失败: {e}\n\n各子任务结果:\n{results_text}"

    # 提取子任务中的图表标记，确保保留在最终回答中
    charts_in_results = re.findall(r'\[CHART\].*?\[/CHART\]', results_text, re.DOTALL)
    if charts_in_results:
        charts_in_answer = re.findall(r'\[CHART\].*?\[/CHART\]', final_answer, re.DOTALL)
        if not charts_in_answer:
            # LLM 丢弃了图表标记，从子任务结果中恢复
            final_answer += '\n\n' + '\n\n'.join(charts_in_results)

    yield {"type": "answer", "content": final_answer, "sources": list(all_sources)}
