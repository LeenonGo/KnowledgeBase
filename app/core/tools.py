"""工具注册表 — 供 Agent / Function Calling 使用"""

from sqlalchemy.orm import Session


# ─── 工具定义（给 LLM 看的 JSON Schema）──

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "在指定知识库中进行语义检索，返回相关文档片段。当需要从知识库中查找信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "检索关键词或问题"
                    },
                    "kb_id": {
                        "type": "string",
                        "description": "知识库 ID。不填则搜索全部可访问的知识库"
                    }
                },
                "required": ["keywords"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_kb",
            "description": "列出当前用户可访问的所有知识库（名称和ID）。当不确定该搜哪个知识库，或用户问'有哪些知识库'时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_doc_content",
            "description": "获取指定文档的完整内容（分块合并）。当检索片段不够、需要查看文档全文时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文档文件名"
                    },
                    "kb_id": {
                        "type": "string",
                        "description": "文档所在的知识库 ID"
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最大返回字符数，默认 10000，最大 30000"
                    }
                },
                "required": ["filename", "kb_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_docs",
            "description": "列出指定知识库下的所有文档。当需要知道某个知识库有哪些文档时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb_id": {
                        "type": "string",
                        "description": "知识库 ID"
                    }
                },
                "required": ["kb_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_doc",
            "description": "对指定文档生成摘要。当用户要求总结某篇文档时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文档文件名"
                    },
                    "kb_id": {
                        "type": "string",
                        "description": "文档所在的知识库 ID"
                    }
                },
                "required": ["filename", "kb_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网获取最新信息。当知识库中没有相关内容或用户需要最新信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "获取当前日期和时间。当用户问今天几号、现在几点、星期几等时间相关问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行数学计算。当需要精确计算数值、百分比、统计等数学运算时使用，不要自己心算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 (100+200)*0.8、2**10、round(3.14159, 2)"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "doc_stats",
            "description": "获取知识库的统计信息，包括文档数量、分块数量、文件格式分布等。当用户问知识库有多大、有多少文档、文档格式分布等统计类问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb_id": {
                        "type": "string",
                        "description": "知识库 ID。不填则统计全部可访问的知识库"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "chart_generator",
            "description": "生成数据可视化图表。当需要用图表展示数据分布、对比、趋势时使用。返回 ECharts 配置，前端自动渲染。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "pie", "line"],
                        "description": "图表类型: bar=柱状图, pie=饼图, line=折线图"
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "分类标签列表（柱状图/折线图的 X 轴，饼图的各区块名称）"
                    },
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "对应的数据值列表"
                    },
                    "value_name": {
                        "type": "string",
                        "description": "数据系列名称（柱状图/折线图的图例名）"
                    }
                },
                "required": ["chart_type", "title", "categories", "values"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "查询当前用户的记忆信息（偏好、背景、纠正记录）。当需要了解用户习惯或历史偏好时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "enum": ["preference", "context", "correction", "all"],
                        "description": "记忆类型筛选，all=全部，默认 all"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_faq",
            "description": "查询常见问题沉淀（FAQ）。高频问答已自动沉淀为 FAQ，命中可直接返回答案，无需重新检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要查询的问题"
                    },
                    "kb_id": {
                        "type": "string",
                        "description": "限定知识库 ID（可选）"
                    }
                },
                "required": ["question"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "knowledge_compare",
            "description": "对比两个知识库或文档的差异。当用户要求对比、比较、分析两个知识库/文档的异同时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb_id_1": {
                        "type": "string",
                        "description": "第一个知识库 ID"
                    },
                    "kb_id_2": {
                        "type": "string",
                        "description": "第二个知识库 ID"
                    },
                    "filename_1": {
                        "type": "string",
                        "description": "第一个知识库中的文档名（可选，不填则对比整个知识库）"
                    },
                    "filename_2": {
                        "type": "string",
                        "description": "第二个知识库中的文档名（可选）"
                    }
                },
                "required": ["kb_id_1", "kb_id_2"]
            }
        }
    },
]


# ─── 工具执行 ──

def execute_tool(
    name: str,
    arguments: dict,
    db: Session,
    user: dict,
) -> str:
    """执行工具调用，返回结果文本。每个工具独立做权限校验。"""
    try:
        if name == "search_kb":
            return _search_kb(arguments, db, user)
        elif name == "list_kb":
            return _list_kb(db, user)
        elif name == "get_doc_content":
            return _get_doc_content(arguments, db, user)
        elif name == "list_docs":
            return _list_docs(arguments, db, user)
        elif name == "summarize_doc":
            return _summarize_doc(arguments, db, user)
        elif name == "web_search":
            return _web_search(arguments)
        elif name == "current_time":
            return _current_time()
        elif name == "calculator":
            return _calculator(arguments)
        elif name == "doc_stats":
            return _doc_stats(arguments, db, user)
        elif name == "chart_generator":
            return _chart_generator(arguments)
        elif name == "recall_memory":
            return _recall_memory(arguments, db, user)
        elif name == "search_faq":
            return _search_faq(arguments, db, user)
        elif name == "knowledge_compare":
            return _knowledge_compare(arguments, db, user)
        else:
            return f"未知工具: {name}"
    except Exception as e:
        print(f"[Tools] 工具 {name} 执行异常: {e}")
        return f"工具执行出错: {str(e)}"


def _search_kb(args: dict, db: Session, user: dict) -> str:
    """知识库检索"""
    from app.api.deps import require_kb_access, get_accessible_kb_ids
    from app.core.vectorstore import search_accessible

    keywords = args.get("keywords", "")
    kb_id = args.get("kb_id")

    if not keywords:
        return "检索关键词不能为空"

    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
        docs = search_accessible(keywords, top_k=8, kb_id=kb_id, use_hybrid=True)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            docs = search_accessible(keywords, top_k=8, use_hybrid=True)
        elif not accessible_ids:
            return "你当前没有可访问的知识库"
        else:
            docs = search_accessible(keywords, top_k=8, accessible_ids=accessible_ids, use_hybrid=True)

    if not docs:
        return "未找到与「{keywords}」相关的内容"

    results = []
    low_count = 0
    for i, d in enumerate(docs, 1):
        # 计算相关度：关键词子串 + 长词权重
        txt = d['text'].lower()
        kw_clean = re.sub(r'[\s?？!！。，,]', '', keywords.lower())
        if len(kw_clean) >= 2:
            # 按 2-gram 和 3-gram 综合评分，长 gram 权重更高
            grams2 = [kw_clean[j:j+2] for j in range(len(kw_clean)-1)]
            grams3 = [kw_clean[j:j+3] for j in range(len(kw_clean)-2)]
            hits2 = sum(1 for g in grams2 if g in txt)
            hits3 = sum(1 for g in grams3 if g in txt)
            ratio = (hits2 / len(grams2) * 0.4 + hits3 / len(grams3) * 0.6) if grams2 and grams3 else 0
        else:
            ratio = 1.0 if kw_clean in txt else 0
        relevance = '高' if ratio >= 0.3 else ('中' if ratio >= 0.15 else '低')
        if relevance == '低':
            low_count += 1
        results.append(f"[C{i} 来源:{d['source']} 相关度:{relevance}]\n{d['text'][:800]}")
    # 全部低相关 → 告知未找到，建议换关键词或联网搜索
    if low_count == len(results):
        return f"未找到与「{keywords}」高度相关的内容。建议：1) 换个关键词重试 2) 使用 web_search 联网搜索"
    return "\n\n".join(results)


def _list_kb(db: Session, user: dict) -> str:
    """列出可访问的知识库"""
    from app.api.deps import get_accessible_kb_ids
    from app.models.models import KnowledgeBase

    accessible_ids = get_accessible_kb_ids(db, user)
    if accessible_ids is None:
        kbs = db.query(KnowledgeBase).filter(KnowledgeBase.status == "active").all()
    elif not accessible_ids:
        return "你当前没有可访问的知识库"
    else:
        kbs = db.query(KnowledgeBase).filter(
            KnowledgeBase.id.in_(accessible_ids),
            KnowledgeBase.status == "active",
        ).all()

    if not kbs:
        return "系统中暂无知识库"

    lines = [f"- {kb.name} (ID: {kb.id})" + (f" — {kb.description[:50]}" if kb.description else "")
             for kb in kbs]
    return "可访问的知识库：\n" + "\n".join(lines)


def _get_doc_content(args: dict, db: Session, user: dict) -> str:
    """获取文档全文 — 从 ChromaDB chunks 合并，支持自定义长度上限"""
    from app.api.deps import require_kb_access
    from app.core.vectorstore import get_chunks

    filename = args.get("filename", "")
    kb_id = args.get("kb_id", "")
    max_chars = min(int(args.get("max_chars", 10000)), 30000)

    if not filename or not kb_id:
        return "需要提供 filename 和 kb_id"

    require_kb_access(db, user, kb_id, "viewer")

    chunks = get_chunks(filename, kb_id)
    if not chunks:
        return f"未找到文档「{filename}」，请用 list_docs 确认文件名"

    # 按 chunk_index 排序后合并
    chunks.sort(key=lambda c: c.get("index", 0))
    full_text = "\n\n".join(c["text"] for c in chunks)
    total_chars = len(full_text)

    if total_chars > max_chars:
        full_text = full_text[:max_chars] + f"\n\n... (文档共 {len(chunks)} 个分块，{total_chars} 字符，已截断至 {max_chars} 字符。如需查看更多内容，可增大 max_chars 参数，最大 30000)"

    return f"文档「{filename}」内容（共 {len(chunks)} 个分块，{total_chars} 字符）：\n\n{full_text}"


def _list_docs(args: dict, db: Session, user: dict) -> str:
    """列出知识库文档"""
    from app.api.deps import require_kb_access
    from app.models.models import Document

    kb_id = args.get("kb_id", "")
    if not kb_id:
        return "需要提供 kb_id"

    require_kb_access(db, user, kb_id, "viewer")

    docs = db.query(Document).filter(
        Document.kb_id == kb_id,
        Document.status.in_(["indexed", "active"]),
    ).all()

    if not docs:
        return "该知识库暂无文档"

    lines = [f"- {doc.filename} ({doc.chunk_count}个分块)" for doc in docs]
    return "知识库文档列表：\n" + "\n".join(lines)


def _summarize_doc(args: dict, db: Session, user: dict) -> str:
    """对文档生成摘要 — 读取全文后调用 LLM"""
    from app.api.deps import require_kb_access
    from app.core.vectorstore import get_chunks
    from app.core.llm import get_llm_client

    filename = args.get("filename", "")
    kb_id = args.get("kb_id", "")

    if not filename or not kb_id:
        return "需要提供 filename 和 kb_id"

    require_kb_access(db, user, kb_id, "viewer")

    chunks = get_chunks(filename, kb_id)
    if not chunks:
        return f"未找到文档「{filename}」，请用 list_docs 确认文件名"

    # 按 chunk_index 排序，取前 20 个分块（避免超长）
    chunks.sort(key=lambda c: c.get("index", 0))
    text = "\n\n".join(c["text"] for c in chunks[:20])
    if len(text) > 12000:
        text = text[:12000]

    client, model, cfg = get_llm_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个文档摘要助手。请对以下文档内容生成简洁的中文摘要，包含主要章节和关键信息。使用 markdown 格式。"},
                {"role": "user", "content": f"文档「{filename}」内容：\n\n{text}"},
            ],
            max_tokens=1024,
            temperature=0.3,
            timeout=30,
        )
        summary = resp.choices[0].message.content
        return f"文档「{filename}」摘要：\n\n{summary}"
    except Exception as e:
        return f"生成摘要失败: {e}"


def _web_search(args: dict) -> str:
    """联网搜索"""
    from app.core.web_search import web_search as _do_search

    query = args.get("query", "")
    if not query:
        return "搜索关键词不能为空"

    return _do_search(query, num_results=5)


def _current_time() -> str:
    """当前时间"""
    from datetime import datetime, timezone, timedelta
    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst)
    weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    return now.strftime(f"%Y年%m月%d日 %H:%M:%S {weekdays[now.weekday()]} (北京时间)")


def _calculator(args: dict) -> str:
    """数学计算 — 安全沙箱执行"""
    import math
    expr = args.get("expression", "")
    if not expr:
        return "请提供数学表达式"

    # 安全白名单：只允许数字、运算符、math 函数
    allowed = set('0123456789+-*/.()%,abcdefghijklmnopqrstuvwxyz_ ')
    if not all(c in allowed for c in expr.lower()):
        return f"表达式包含不允许的字符: {expr}"
    # 阻止属性访问攻击（dunder 方法）
    if '__' in expr:
        return "表达式不允许包含双下划线"

    # 允许的 math 函数
    safe_dict = {
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'sum': sum, 'pow': pow, 'int': int, 'float': float,
        'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'pi': math.pi, 'e': math.e, 'ceil': math.ceil, 'floor': math.floor,
    }
    try:
        result = eval(expr, {"__builtins__": {}}, safe_dict)
        return f"{expr} = {result}"
    except Exception as e:
        return f"计算失败: {e}"


def _doc_stats(args: dict, db: Session, user: dict) -> str:
    """知识库统计"""
    from app.api.deps import get_accessible_kb_ids
    from app.models.models import KnowledgeBase, Document
    from sqlalchemy import func

    kb_id = args.get("kb_id", "")

    if kb_id:
        # 单个知识库统计
        from app.api.deps import require_kb_access
        require_kb_access(db, user, kb_id, "viewer")
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if not kb:
            return "知识库不存在"
        docs = db.query(Document).filter(Document.kb_id == kb_id, Document.status.in_(["indexed", "active"])).all()
        total_chunks = sum(d.chunk_count or 0 for d in docs)
        ext_dist = {}
        for d in docs:
            ext = (d.filename or "").rsplit(".", 1)[-1].lower() if "." in (d.filename or "") else "unknown"
            ext_dist[ext] = ext_dist.get(ext, 0) + 1
        lines = [f"知识库「{kb.name}」统计：", f"- 文档数: {len(docs)}", f"- 分块总数: {total_chunks}"]
        if ext_dist:
            lines.append("- 格式分布: " + ", ".join(f"{k}({v})" for k, v in sorted(ext_dist.items(), key=lambda x: -x[1])))
        return "\n".join(lines)
    else:
        # 全部知识库统计
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            kbs = db.query(KnowledgeBase).filter(KnowledgeBase.status == "active").all()
        elif not accessible_ids:
            return "你当前没有可访问的知识库"
        else:
            kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(accessible_ids), KnowledgeBase.status == "active").all()

        lines = ["全部知识库统计："]
        total_docs = 0
        total_chunks = 0
        for kb in kbs:
            docs = db.query(Document).filter(Document.kb_id == kb.id, Document.status.in_(["indexed", "active"])).all()
            chunks = sum(d.chunk_count or 0 for d in docs)
            total_docs += len(docs)
            total_chunks += chunks
            lines.append(f"- {kb.name}: {len(docs)} 个文档, {chunks} 个分块")
        lines.insert(1, f"- 知识库总数: {len(kbs)}")
        lines.insert(2, f"- 文档总数: {total_docs}")
        lines.insert(3, f"- 分块总数: {total_chunks}")
        return "\n".join(lines)


def _chart_generator(args: dict) -> str:
    """生成 ECharts 图表配置"""

    chart_type = args.get("chart_type", "bar")
    title = args.get("title", "")
    categories = args.get("categories", [])
    values = args.get("values", [])
    value_name = args.get("value_name", "数量")

    if not categories or not values:
        return "需要提供 categories 和 values"
    if len(categories) != len(values):
        return f"categories({len(categories)}) 和 values({len(values)}) 长度不一致"

    # 生成 ECharts option
    if chart_type == "pie":
        option = {
            "title": {"text": title, "left": "center", "textStyle": {"fontSize": 14}},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%})"},
            "series": [{
                "type": "pie", "radius": "55%", "center": ["50%", "55%"],
                "data": [{"name": categories[i], "value": values[i]} for i in range(len(categories))],
                "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0,0,0,0.5)"}}
            }]
        }
    else:
        option = {
            "title": {"text": title, "left": "center", "textStyle": {"fontSize": 14}},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 30 if categories and len(max(categories, key=len)) > 6 else 0}},
            "yAxis": {"type": "value"},
            "series": [{"name": value_name, "type": chart_type, "data": values,
                        "itemStyle": {"color": "#1890ff"}, "barMaxWidth": 40}]
        }

    # 加标记让前端识别
    return f"[CHART]{json.dumps(option, ensure_ascii=False)}[/CHART]"


def _knowledge_compare(args: dict, db: Session, user: dict) -> str:
    """对比两个知识库"""
    from app.api.deps import require_kb_access
    from app.models.models import KnowledgeBase, Document
    from app.core.vectorstore import get_chunks

    kb_id_1 = args.get("kb_id_1", "")
    kb_id_2 = args.get("kb_id_2", "")
    fn_1 = args.get("filename_1", "")
    fn_2 = args.get("filename_2", "")

    if not kb_id_1 or not kb_id_2:
        return "需要提供两个知识库 ID"

    require_kb_access(db, user, kb_id_1, "viewer")
    require_kb_access(db, user, kb_id_2, "viewer")

    kb1 = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id_1).first()
    kb2 = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id_2).first()
    if not kb1 or not kb2:
        return "知识库不存在"

    def get_content(kb_id, filename):
        if filename:
            chunks = get_chunks(filename, kb_id)
            if chunks:
                chunks.sort(key=lambda c: c.get("index", 0))
                text = "\n".join(c["text"] for c in chunks[:10])
                return f"文档「{filename}」内容：\n{text[:3000]}"
            return f"未找到文档「{filename}」"
        else:
            docs = db.query(Document).filter(Document.kb_id == kb_id, Document.status.in_(["indexed", "active"])).all()
            lines = []
            for d in docs[:5]:
                chunks = get_chunks(d.filename, kb_id)
                preview = chunks[0]["text"][:200] if chunks else "(空)"
                lines.append(f"- {d.filename}: {preview}...")
            return f"知识库文档({len(docs)}个)：\n" + "\n".join(lines)

    content_1 = get_content(kb_id_1, fn_1)
    content_2 = get_content(kb_id_2, fn_2)

    return f"=== {kb1.name} ===\n{content_1}\n\n=== {kb2.name} ===\n{content_2}"

def _recall_memory(args: dict, db: Session, user: dict) -> str:
    """查询用户记忆"""
    from app.core.memory_service import get_user_memories, record_memory_hit

    user_id = user.get("sub", "")
    mem_type = args.get("memory_type", "all")

    memories = get_user_memories(db, user_id)
    if not memories:
        return "暂无用户记忆记录"

    if mem_type != "all":
        memories = [m for m in memories if m["memory_type"] == mem_type]

    if not memories:
        return f"暂无类型为「{mem_type}」的记忆记录"

    # 记录命中
    record_memory_hit(db, [m["id"] for m in memories[:10]])

    type_labels = {"preference": "偏好", "context": "背景", "correction": "纠正"}
    lines = []
    for m in memories[:15]:
        label = type_labels.get(m["memory_type"], m["memory_type"])
        lines.append(f"- [{label}] {m['content']}（引用{m['hit_count']}次）")

    return "用户记忆：\n" + "\n".join(lines)


def _search_faq(args: dict, db: Session, user: dict) -> str:
    """搜索 FAQ 沉淀"""
    from app.core.memory_service import search_faq as _do_search_faq
    from app.api.deps import get_accessible_kb_ids

    question = args.get("question", "")
    kb_id = args.get("kb_id")

    if not question:
        return "请提供查询问题"

    accessible_ids = get_accessible_kb_ids(db, user)
    result = _do_search_faq(db, question, kb_id=kb_id, accessible_ids=accessible_ids)

    if not result:
        return "未找到匹配的 FAQ"

    status_label = {"auto": "（自动沉淀）", "approved": "（已审核）"}.get(result["status"], "")
    tags = f" 标签:{','.join(result['tags'])}" if result.get("tags") else ""

    return f"FAQ 命中{status_label}{tags}\n问题：{result['question']}\n回答：{result['answer']}"

