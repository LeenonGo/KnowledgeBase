"""SQL 分析助手 API — 自然语言查询电商数据库"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.database import get_db
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api/sql", tags=["SQL 分析"])


class SQLQueryRequest(BaseModel):
    """自然语言查询请求"""
    question: str = Field(..., min_length=1, max_length=500, description="自然语言问题")
    history: Optional[List[dict]] = Field(default=None, description="多轮对话历史")


class SQLExecuteRequest(BaseModel):
    """直接执行 SQL 请求"""
    sql: str = Field(..., min_length=1, max_length=5000, description="SQL 查询语句")


@router.post("/query")
async def sql_query(
    req: SQLQueryRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    自然语言查询 — SSE 流式返回

    事件流：
      event: sql       → 生成的 SQL + 思考过程
      event: result    → 查询结果（列名 + 数据行）
      event: analysis  → 分析总结 + 图表建议
      event: error     → 错误信息
    """
    from app.core.sql_agent import get_sql_agent

    agent = get_sql_agent()

    # 构建历史上下文
    history = None
    if req.history:
        history = []
        for h in req.history[-6:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})

    def stream_gen():
        try:
            for event in agent.query(req.question, history):
                step = event["step"]
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {step}\ndata: {data}\n\n"

            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    log_audit(db, user, "sql_query", req.question[:100], "自然语言SQL查询", "success")
    return StreamingResponse(stream_gen(), media_type="text/event-stream")


@router.post("/execute")
async def sql_execute(
    req: SQLExecuteRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """直接执行 SQL（编辑后手动执行）"""
    from app.core.sql_agent import get_sql_agent

    agent = get_sql_agent()
    result = agent.execute_sql_direct(req.sql)

    log_audit(db, user, "sql_execute", req.sql[:100], "直接执行SQL", "success")
    return result


@router.get("/schema")
async def sql_schema(
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """获取数据库表结构"""
    from app.core.sql_agent import get_sql_agent

    agent = get_sql_agent()
    return agent.schema.get_schema_struct()
