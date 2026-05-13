"""
人机协作确认机制 — Agent 执行暂停/恢复

机制：
1. Agent 流式执行到暂停点时，yield approval_request 事件后结束
2. 前端展示确认按钮，用户操作后调用 /query/agent/resume
3. resume 接口从存储的状态恢复执行

状态存储：内存 dict，按 user_id + session_id 隔离
"""

import time
import threading
from typing import Generator

# ─── 审批状态存储 ─────────────────────────────────────

# {session_id: {user_id, question, context, history, tools, tool_context,
#               phase, plan_data, tasks, current_task_idx, all_results, all_sources}}
_approval_sessions: dict = dict()
_approval_lock = threading.Lock()

# session_id 递增计数器
_session_counter = 0
_counter_lock = threading.Lock()


def create_session(user_id: str, question: str, context: str, history: str,
                   tools: list, tool_context: dict, plan_data: dict,
                   tasks: list) -> str:
    """创建审批会话，返回 session_id"""
    global _session_counter
    with _counter_lock:
        _session_counter += 1
        sid = f"approval-{user_id}-{_session_counter}-{int(time.time())}"

    with _approval_lock:
        _approval_sessions[sid] = {
            "user_id": user_id,
            "question": question,
            "context": context,
            "history": history,
            "tools": tools,
            "tool_context": tool_context,
            "plan_data": plan_data,
            "tasks": tasks,
            "current_task_idx": 0,
            "all_results": [],
            "all_sources": set(),
            "created_at": time.time(),
        }
    return sid


def get_session(session_id: str) -> dict | None:
    """获取审批会话"""
    with _approval_lock:
        return _approval_sessions.get(session_id)


def remove_session(session_id: str):
    """删除审批会话"""
    with _approval_lock:
        _approval_sessions.pop(session_id, None)


def cleanup_expired(max_age: int = 600):
    """清理过期会话（超过 max_age 秒）"""
    now = time.time()
    with _approval_lock:
        expired = [sid for sid, s in _approval_sessions.items()
                   if now - s.get("created_at", now) > max_age]
        for sid in expired:
            _approval_sessions.pop(sid, None)
    return len(expired)
