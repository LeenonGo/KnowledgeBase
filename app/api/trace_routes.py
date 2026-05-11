"""全链路 Trace API — 查询 Trace 列表和详情"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.models.models import Trace, TraceSpan
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["Trace"])


@router.get("/traces")
async def list_traces(
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 Trace 列表（仅管理员可查看全部）"""
    role = user.get("role", "user")
    q = db.query(Trace)

    # 非管理员只看自己的
    if role not in ("super_admin", "kb_admin"):
        q = q.filter(Trace.user_id == user.get("sub"))

    total = q.count()
    traces = q.order_by(desc(Trace.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for t in traces:
        items.append({
            "id": t.id,
            "user_id": t.user_id,
            "question": t.question[:100] if t.question else "",
            "total_duration_ms": t.total_duration_ms,
            "span_count": len(t.spans) if t.spans else 0,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        })

    return {"total": total, "items": items}


@router.get("/traces/{trace_id}")
async def get_trace_detail(
    trace_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 Trace 详情（含所有 Span）"""
    trace = db.query(Trace).filter(Trace.id == trace_id).first()
    if not trace:
        raise HTTPException(404, "Trace 不存在")

    # 权限检查
    role = user.get("role", "user")
    if role not in ("super_admin", "kb_admin") and trace.user_id != user.get("sub"):
        raise HTTPException(403, "无权查看此 Trace")

    spans = db.query(TraceSpan).filter(
        TraceSpan.trace_id == trace_id
    ).order_by(TraceSpan.seq).all()

    return {
        "id": trace.id,
        "user_id": trace.user_id,
        "question": trace.question,
        "total_duration_ms": trace.total_duration_ms,
        "created_at": trace.created_at.isoformat() if trace.created_at else "",
        "spans": [
            {
                "id": s.id,
                "name": s.name,
                "duration_ms": s.duration_ms,
                "input_preview": s.input_preview,
                "output_preview": s.output_preview,
                "seq": s.seq,
            }
            for s in spans
        ],
    }
