"""问答 & 重建索引 API — 含缓存 + 查询改写"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.cache import query_cache
from app.models.schema import QueryRequest, QueryResponse
from app.models.models import ConversationTurn
from app.api.deps import get_current_user, log_audit, require_kb_access, get_accessible_kb_ids

router = APIRouter(prefix="/api", tags=["问答"])



def _get_conversation_history(conv_id: str, db: Session, max_turns: int = 3) -> str:
    """从数据库获取对话历史"""
    turns = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conv_id,
    ).order_by(ConversationTurn.created_at.desc()).limit(max_turns * 2).all()

    if not turns:
        return ""

    # 按时间正序排列
    turns = list(reversed(turns))
    history_parts = []
    for t in turns:
        role = "用户" if t.role == "user" else "助手"
        content = t.content[:200]  # 截断避免过长
        history_parts.append(f"{role}: {content}")

    return "\n".join(history_parts)


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(
    request: Request, req: QueryRequest,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    from app.core.trace import TraceContext

    # ── 全链路 Trace ──
    trace = TraceContext(user_id=user.get("sub"), question=req.question, db=db)
    trace.__enter__()

    # ── 1. 获取对话历史 ──
    history = req.history or ""
    if req.conv_id and not history:
        history = _get_conversation_history(req.conv_id, db)

    # ── 2. 查缓存 ──
    search_question = req.question
    _uid = user.get("sub")
    _cache_key = query_cache.make_key(
        req.question, kb_id=req.kb_id, user_id=_uid,
        use_agent=req.use_agent, use_polish=req.use_polish, use_rewrite=req.use_rewrite,
    )
    cached = query_cache.get(_cache_key)
    if cached:
        log_audit(db, user, "query", req.question[:100], "缓存命中", "success",
                   request.client.host if request.client else "")
        return QueryResponse(**cached)

    # ── 3. 查询改写 + 润色（缓存未命中时才执行）──
    if history and req.use_rewrite:
        from app.core.llm import rewrite_query
        try:
            rewritten = rewrite_query(req.question, history)
            if rewritten and rewritten != req.question and len(rewritten) > 5:
                search_question = rewritten
                print(f"[QueryRewrite] '{req.question[:50]}' → '{search_question[:50]}'")
        except Exception as e:
            print(f"[QueryRewrite] 改写失败，使用原始问题: {e}")

    # ── 3.5 Query 润色（可选）──
    from app.core.llm import generate_answer, generate_answer_agent, get_refuse_answer
    search_keywords = None
    if req.use_polish:
        from app.core.llm import polish_query
        polished = polish_query(search_question)
        search_question = polished.get("expanded") or polished.get("corrected", search_question)
        search_keywords = polished.get("keywords") or None
    print(f"[QueryPolish] expanded={search_question[:80]} keywords={search_keywords}")

    # ── 4. 检索 ──
    from app.core.vectorstore import search_accessible
    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")
        docs = search_accessible(search_question, top_k=req.top_k, kb_id=req.kb_id,
                                 use_hybrid=req.use_hybrid, use_reranker=req.use_reranker,
                                 keywords=search_keywords)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        docs = search_accessible(search_question, top_k=req.top_k,
                                 accessible_ids=accessible_ids,
                                 use_hybrid=req.use_hybrid, use_reranker=req.use_reranker,
                                 keywords=search_keywords)

    # ── 5. 拒答处理 ──
    if not docs:
        # 联网搜索兜底（非 Agent 模式下）
        if req.use_web_search and not req.use_agent:
            from app.core.web_search import web_search as _web_search
            web_result = _web_search(req.question)
            if web_result and "未配置" not in web_result:
                answer = generate_answer(req.question, web_result, history=history)
                trace.span("web_search", input=req.question[:200], output=web_result[:200])
                trace.__exit__(None, None, None)
                result = {"question": req.question, "answer": answer, "sources": ["互联网搜索"], "citations": []}
                return QueryResponse(**result)
        log_audit(db, user, "query", req.question[:100], "未命中", "success",
                   request.client.host if request.client else "")
        refuse = get_refuse_answer()
        result = {"question": req.question, "answer": refuse, "sources": [], "citations": []}
        query_cache.set(_cache_key, result, ttl=300)
        trace.__exit__(None, None, None)
        return QueryResponse(**result)

    # ── 6. 拼上下文 + 生成回答（带引用标注）──
    from app.core.llm import format_context_with_citations, parse_citations
    MAX_CONTEXT_CHARS = 3000

    context, citation_map = format_context_with_citations(docs)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "..."

    sources = list(set(d["source"] for d in docs))

    # ── 6.5 Agent 模式 or 普通模式 ──
    if req.use_agent:
        from app.core.tools import TOOL_DEFINITIONS
        # Agent 模式：不注入检索 context，让 LLM 主动调工具
        agent_tools = list(TOOL_DEFINITIONS)
        # 联网搜索工具（按需添加）
        if req.use_web_search:
            agent_tools.append({
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索互联网获取最新信息，当知识库中没有相关内容时使用",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                        "required": ["query"],
                    },
                },
            })
        agent_context = "（请使用可用工具来查找信息回答用户问题）"
        answer = generate_answer_agent(
            req.question, agent_context, history=history,
            tools=agent_tools,
            tool_context={"db": db, "user": user},
        )
        citations = []
    else:
        answer = generate_answer(req.question, context, history=history)
        # 解析引用标注 [C1] → [1]
        answer, citations = parse_citations(answer, citation_map)

    result = {"question": req.question, "answer": answer, "sources": sources, "citations": citations}
    query_cache.set(_cache_key, result, ttl=3600)

    trace.span("retrieval", input=req.question[:200], output=f"命中{len(docs)}条")
    trace.span("generation", input=context[:200], output=answer[:200])
    trace.__exit__(None, None, None)

    log_audit(db, user, "query", req.question[:100],
               f"命中{len(docs)}条, 来源={sources}", "success",
               request.client.host if request.client else "")
    return QueryResponse(**result)


@router.post("/query/stream")
async def query_stream(
    request: Request, req: QueryRequest,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    """流式问答"""
    from app.core.llm import generate_answer_stream, get_refuse_answer
    from app.core.vectorstore import search_accessible

    # ── 1. 获取对话历史 ──
    history = req.history or ""
    if req.conv_id and not history:
        history = _get_conversation_history(req.conv_id, db)

    # ── 2. 查询改写 + 润色 ──
    search_question = req.question
    if history and req.use_rewrite:
        from app.core.llm import rewrite_query
        try:
            rewritten = rewrite_query(req.question, history)
            if rewritten and rewritten != req.question and len(rewritten) > 5:
                search_question = rewritten
        except Exception as e:
            print(f"[QueryRewrite] 改写失败: {e}")

    search_keywords = None
    if req.use_polish:
        from app.core.llm import polish_query
        polished = polish_query(search_question)
        search_question = polished.get("expanded") or polished.get("corrected", search_question)
        search_keywords = polished.get("keywords") or None

    # ── 3. 检索 ──
    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")
        docs = search_accessible(search_question, top_k=req.top_k, kb_id=req.kb_id,
                                 use_hybrid=req.use_hybrid, use_reranker=req.use_reranker,
                                 keywords=search_keywords)
    else:
        accessible_ids = get_accessible_kb_ids(db, user)
        docs = search_accessible(search_question, top_k=req.top_k,
                                 accessible_ids=accessible_ids,
                                 use_hybrid=req.use_hybrid, use_reranker=req.use_reranker,
                                 keywords=search_keywords)

    # ── 4. 拒答处理 ──
    if not docs:
        # 联网搜索兜底
        if req.use_web_search:
            from app.core.web_search import web_search as _web_search
            web_result = _web_search(req.question)
            if web_result and "未配置" not in web_result:
                answer = generate_answer(req.question, web_result, history=history)
                async def web_gen():
                    for ch in [answer[i:i+50] for i in range(0, len(answer), 50)]:
                        yield 'event: token\ndata: ' + json.dumps(ch) + '\n\n'
                    done_data = json.dumps({'sources': ['互联网搜索'], 'citations': []})
                    yield 'event: done\ndata: ' + done_data + '\n\n'
                return StreamingResponse(web_gen(), media_type="text/event-stream")
        refuse = get_refuse_answer()
        async def refuse_gen():
            yield 'event: token\ndata: ' + json.dumps(refuse) + '\n\n'
            done_data = json.dumps({'sources': [], 'citations': []})
            yield 'event: done\ndata: ' + done_data + '\n\n'
        return StreamingResponse(refuse_gen(), media_type="text/event-stream")

    # ── 5. 拼上下文（带引用标注）──
    from app.core.llm import format_context_with_citations, parse_citations
    MAX_CONTEXT_CHARS = 3000

    context, citation_map = format_context_with_citations(docs)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "..."

    sources = list(set(d["source"] for d in docs))

    # ── 6. 流式生成 ──
    async def stream_gen():
        try:
            full_answer = ""
            for event in generate_answer_stream(req.question, context, history=history):
                if event['type'] == 'token':
                    full_answer += event['content']
                    yield 'event: token\ndata: ' + json.dumps(event['content']) + '\n\n'
                elif event['type'] == 'source':
                    src_data = json.dumps({'source': event['source']})
                    yield 'event: source\ndata: ' + src_data + '\n\n'
            # 直接从 citation_map 构建 citations（不改文本，前端统一处理替换）
            _cites = []
            for _k, _v in citation_map.items():
                _num = int(_k[1:]) if _k[1:].isdigit() else 0
                _cites.append({"index": _num, "source": _v.get("source", ""), "text_preview": _v.get("text_preview", "")})
            _cites.sort(key=lambda x: x["index"])
            done_data = json.dumps({'sources': sources, 'citations': _cites})
            yield 'event: done\ndata: ' + done_data + '\n\n'
        except Exception as e:
            yield 'event: error\ndata: ' + json.dumps(str(e)) + '\n\n'

    log_audit(db, user, "query", req.question[:100],
              f"流式问答, kb={req.kb_id or '全部'}", "success",
              request.client.host if request.client else "")
    return StreamingResponse(stream_gen(), media_type="text/event-stream")




@router.post("/query/agent/stream")
async def agent_query_stream(
    request: Request, req: QueryRequest,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Agent 模式流式问答 — Plan-and-Execute + 推理链可视化"""
    from app.core.llm import plan_and_execute_stream, get_refuse_answer
    from app.core.vectorstore import search_accessible
    from app.core.tools import TOOL_DEFINITIONS

    # 获取对话历史
    history = req.history or ""
    if req.conv_id and not history:
        history = _get_conversation_history(req.conv_id, db)

    # 权限检查
    if req.kb_id:
        require_kb_access(db, user, req.kb_id, "viewer")

    async def agent_stream_gen():
        try:
            agent_context = "（请使用可用工具来查找信息回答用户问题）"
            # 组装工具列表：基础工具 + 可选联网搜索
            agent_tools = list(TOOL_DEFINITIONS)
            if req.use_web_search:
                from app.core.tools import TOOL_DEFINITIONS as _TD
                # web_search 已在 TOOL_DEFINITIONS 中，无需重复添加
                pass
            for event in plan_and_execute_stream(
                req.question, agent_context, history=history,
                tools=agent_tools,
                tool_context={"db": db, "user": user},
            ):
                event_type = event["type"]
                if event_type == "plan":
                    data = json.dumps(event, ensure_ascii=False)
                    yield f"event: plan\ndata: {data}\n\n"
                elif event_type == "subtask_start":
                    data = json.dumps(event, ensure_ascii=False)
                    yield f"event: subtask_start\ndata: {data}\n\n"
                elif event_type == "subtask_done":
                    data = json.dumps(event, ensure_ascii=False)
                    yield f"event: subtask_done\ndata: {data}\n\n"
                elif event_type == "thought":
                    data = json.dumps({"step": event["step"], "content": event["content"]})
                    yield f"event: thought\ndata: {data}\n\n"
                elif event_type == "action":
                    data = json.dumps({"step": event["step"], "tool": event["tool"],
                                       "arguments": event["arguments"]})
                    yield f"event: action\ndata: {data}\n\n"
                elif event_type == "observe":
                    data = json.dumps({"step": event["step"], "content": event["content"]})
                    yield f"event: observe\ndata: {data}\n\n"
                elif event_type == "answer":
                    data = json.dumps({"content": event["content"], "sources": event.get("sources", []), "citations": event.get("citations", [])})
                    yield f"event: answer\ndata: {data}\n\n"
                elif event_type == "error":
                    data = json.dumps({"content": event["content"]})
                    yield f"event: error\ndata: {data}\n\n"
        except Exception as e:
            yield f"event: error\ndata: " + json.dumps(str(e)) + "\n\n"

    log_audit(db, user, "query", req.question[:100],
              f"Agent流式问答, kb={req.kb_id or '全部'}", "success",
              request.client.host if request.client else "")
    return StreamingResponse(agent_stream_gen(), media_type="text/event-stream")

@router.get("/cache/stats")
async def get_cache_stats(user: dict = Depends(get_current_user)):
    """查询缓存统计"""
    return query_cache.stats()


@router.post("/cache/clear")
async def clear_cache(user: dict = Depends(get_current_user)):
    """清空查询缓存"""
    query_cache.clear()
    return {"message": "缓存已清空"}


@router.post("/reindex")
async def reindex(
    request: Request, kb_id: str = None,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    from app.core.vectorstore import reindex_kb

    if kb_id:
        require_kb_access(db, user, kb_id, "editor")

    count = reindex_kb(kb_id)
    if count == 0:
        return {"message": "没有需要重建的文档", "count": 0}

    query_cache.clear()

    log_audit(db, user, "reindex", kb_id or "全部", f"重建{count}个向量", "success",
               request.client.host if request.client else "")
    return {"message": "索引重建完成", "count": count}
