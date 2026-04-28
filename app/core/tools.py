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
        else:
            return f"未知工具: {name}"
    except Exception as e:
        print(f"[Tools] 工具 {name} 执行异常: {e}")
        return f"工具执行出错: {str(e)}"


def _search_kb(args: dict, db: Session, user: dict) -> str:
    """知识库检索"""
    from app.api.deps import require_kb_access, get_accessible_kb_ids
    from app.core.vectorstore import query as vector_query

    keywords = args.get("keywords", "")
    kb_id = args.get("kb_id")

    if not keywords:
        return "检索关键词不能为空"

    if kb_id:
        require_kb_access(db, user, kb_id, "viewer")
        docs = vector_query(keywords, top_k=5, kb_id=kb_id, use_hybrid=True)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        if accessible_ids is None:
            docs = vector_query(keywords, top_k=5, use_hybrid=True)
        elif not accessible_ids:
            return "你当前没有可访问的知识库"
        else:
            all_docs = []
            for kid in accessible_ids:
                all_docs.extend(vector_query(keywords, top_k=5, kb_id=kid, use_hybrid=True))
            all_docs.sort(key=lambda x: x.get("distance", 0))
            docs = all_docs[:5]

    if not docs:
        return f"未找到与「{keywords}」相关的内容"

    results = []
    for i, d in enumerate(docs, 1):
        results.append(f"[结果{i} 来源:{d['source']}]\n{d['text'][:500]}")
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
