"""全链路 Trace — 基于 contextvars 的上下文追踪"""

import time
import contextvars
from typing import Any

# 当前 Trace 上下文（线程安全 / 异步安全）
_current_trace: contextvars.ContextVar = contextvars.ContextVar("current_trace", default=None)


class TraceContext:
    """
    Trace 上下文管理器。
    用法:
        with TraceContext(user_id="u1", question="xxx", db=db) as trace:
            trace.span("retrieval", input="...", output="...")
            trace.span("generation", input="...", output="...")
    """

    def __init__(self, user_id: str = None, question: str = "", db: Any = None):
        self.user_id = user_id
        self.question = question
        self.db = db
        self.trace_id = None
        self.spans: list[dict] = []
        self._seq = 0
        self._start_time = None
        self._token = None

    def __enter__(self):
        from app.models.models import Trace, TraceSpan
        self._start_time = time.time()

        # 创建 Trace 记录
        if self.db:
            try:
                trace_record = Trace(
                    user_id=self.user_id,
                    question=self.question[:2000],
                    total_duration_ms=0,
                )
                self.db.add(trace_record)
                self.db.flush()
                self.trace_id = trace_record.id
            except Exception as e:
                print(f"[Trace] 创建 Trace 记录失败: {e}")
                self.db.rollback()

        # 设置上下文
        self._token = _current_trace.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 计算总耗时
        total_ms = int((time.time() - self._start_time) * 1000)

        # 批量写入 Span 记录
        if self.db and self.trace_id:
            try:
                from app.models.models import Trace, TraceSpan
                # 更新 Trace 总耗时
                trace_record = self.db.query(Trace).filter(Trace.id == self.trace_id).first()
                if trace_record:
                    trace_record.total_duration_ms = total_ms

                # 批量插入 Spans
                for span_data in self.spans:
                    span = TraceSpan(
                        trace_id=self.trace_id,
                        name=span_data["name"],
                        duration_ms=span_data["duration_ms"],
                        input_preview=span_data.get("input_preview", "")[:2000],
                        output_preview=span_data.get("output_preview", "")[:2000],
                        seq=span_data["seq"],
                    )
                    self.db.add(span)
                self.db.commit()
            except Exception as e:
                print(f"[Trace] 保存 Span 记录失败: {e}")
                self.db.rollback()

        # 恢复上下文
        if self._token is not None:
            _current_trace.reset(self._token)

    def span(self, name: str, input: str = "", output: str = ""):
        """
        记录一个 Span。

        Args:
            name: Span 名称（如 retrieval / rewrite / generation）
            input: 输入预览（自动截断至 2000 字符）
            output: 输出预览（自动截断至 2000 字符）
        """
        self._seq += 1
        span_data = {
            "name": name,
            "duration_ms": 0,  # 简化版本不做嵌套计时
            "input_preview": str(input)[:2000],
            "output_preview": str(output)[:2000],
            "seq": self._seq,
        }
        self.spans.append(span_data)
        return span_data


def get_current_trace() -> TraceContext | None:
    """获取当前 Trace 上下文"""
    return _current_trace.get(None)
