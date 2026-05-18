"""SQL 分析助手 API — 自然语言查询电商数据库"""

import json
import time

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
    output_format: str = Field(default="table", description="输出格式: json / table / report")


class SQLExecuteRequest(BaseModel):
    """直接执行 SQL 请求"""
    sql: str = Field(..., min_length=1, max_length=5000, description="SQL 查询语句")


def _save_query_audit(db, user, question, generated_sql, output_format,
                       row_count, elapsed_ms, total_ms, error, status):
    """保存查询审计日志"""
    from app.models.models import QueryAuditLog
    try:
        log = QueryAuditLog(
            user_id=user.get("sub", ""),
            username=user.get("username", ""),
            question=question,
            generated_sql=generated_sql,
            output_format=output_format,
            row_count=row_count,
            elapsed_ms=elapsed_ms,
            total_ms=total_ms,
            error=error,
            status=status,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("kb").error(f"保存审计日志失败: {e}")


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
      event: analysis  → 分析总结 + 图表建议（含 output_format）
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

    output_format = req.output_format if req.output_format in ("json", "table", "report") else "table"

    def stream_gen():
        start_time = time.time()
        generated_sql = ""
        row_count = 0
        elapsed_ms = 0
        error_msg = ""
        status = "success"

        try:
            for event in agent.query(req.question, history, output_format=output_format):
                step = event["step"]
                data = json.dumps(event["data"], ensure_ascii=False)

                # 采集审计信息
                if step == "sql":
                    generated_sql = event["data"].get("sql", "")
                elif step == "result":
                    row_count = event["data"].get("row_count", 0)
                    elapsed_ms = event["data"].get("elapsed_ms", 0)
                    if event["data"].get("error"):
                        error_msg = event["data"]["error"]
                        status = "error"

                yield f"event: {step}\ndata: {data}\n\n"

            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            error_msg = str(e)
            status = "error"
            error_data = json.dumps({"error": error_msg}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"
        finally:
            total_ms = int((time.time() - start_time) * 1000)
            _save_query_audit(
                db, user, req.question, generated_sql, output_format,
                row_count, elapsed_ms, total_ms, error_msg, status
            )

    log_audit(db, user, "sql_query", req.question[:100],
              f"SQL查询({output_format})", "success")
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


@router.get("/audit-logs")
async def get_query_audit_logs(
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    username: str = None,
    output_format: str = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """查询审计日志 — super_admin 查全部，普通用户查自己的"""
    from app.models.models import QueryAuditLog

    q = db.query(QueryAuditLog)

    # 权限过滤
    if user.get("role") != "super_admin":
        q = q.filter(QueryAuditLog.user_id == user.get("sub", ""))

    if status:
        q = q.filter(QueryAuditLog.status == status)
    if username and user.get("role") == "super_admin":
        q = q.filter(QueryAuditLog.username == username)
    if output_format:
        q = q.filter(QueryAuditLog.output_format == output_format)

    total = q.count()
    logs = q.order_by(QueryAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "id": l.id,
            "username": l.username,
            "question": l.question,
            "generated_sql": l.generated_sql,
            "output_format": l.output_format,
            "row_count": l.row_count,
            "elapsed_ms": l.elapsed_ms,
            "total_ms": l.total_ms,
            "error": l.error,
            "status": l.status,
            "created_at": str(l.created_at),
        } for l in logs]
    }
