"""上传任务进度追踪"""

import threading
import time
from typing import Any

# 存储每个任务的进度: {task_id: {stage, current_page, total_pages, percent, message, result, error, done}}
_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def create_task(task_id: str, total_pages: int = 0) -> None:
    with _lock:
        _tasks[task_id] = {
            "stage": "uploading",
            "current_page": 0,
            "total_pages": total_pages,
            "percent": 0,
            "message": "文件上传中...",
            "result": None,
            "error": None,
            "done": False,
        }


def update(task_id: str, **kwargs) -> None:
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


def finish(task_id: str, result: dict = None, error: str = None) -> None:
    with _lock:
        if task_id in _tasks:
            _tasks[task_id]["done"] = True
            _tasks[task_id]["stage"] = "done"
            _tasks[task_id]["percent"] = 100
            if result:
                _tasks[task_id]["result"] = result
            if error:
                _tasks[task_id]["error"] = error
                _tasks[task_id]["message"] = f"处理失败: {error}"
            else:
                _tasks[task_id]["message"] = "处理完成"


def get(task_id: str) -> dict | None:
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task else None


def cleanup(task_id: str) -> None:
    with _lock:
        _tasks.pop(task_id, None)
