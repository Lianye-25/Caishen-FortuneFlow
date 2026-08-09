"""
财神上下左右 — 任务状态管理

用 JSON 文件做任务队列，纯标准库零依赖。
"""

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

CN_TZ = timezone(timedelta(hours=8))

# 默认任务存储路径
DEFAULT_TASKS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "tasks.json"
)
DEFAULT_TASKS_PATH = os.path.normpath(DEFAULT_TASKS_PATH)

_lock = threading.Lock()


def _load_tasks(tasks_path: str) -> list[dict]:
    """加载任务列表（线程安全）。"""
    if not os.path.exists(tasks_path):
        return []
    with open(tasks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def _save_tasks(tasks: list[dict], tasks_path: str) -> None:
    """保存任务列表（线程安全）。"""
    os.makedirs(os.path.dirname(tasks_path), exist_ok=True)
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False, indent=2)


def _generate_task_id() -> str:
    """生成唯一任务ID。"""
    now = datetime.now(CN_TZ)
    return f"task-{now.strftime('%Y%m%d%H%M%S')}-{now.microsecond:06d}"


def create_task(
    direction: str,
    target_name: str,
    content: Optional[str],
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> str:
    """创建新任务，返回任务ID。"""
    task_id = _generate_task_id()
    task = {
        "id": task_id,
        "direction": direction,
        "target_name": target_name,
        "content": content,
        "status": "pending",
        "result": None,
        "error": None,
        "created_at": datetime.now(CN_TZ).isoformat(),
        "completed_at": None,
    }
    with _lock:
        tasks = _load_tasks(tasks_path)
        tasks.append(task)
        _save_tasks(tasks, tasks_path)
    return task_id


def update_task(
    task_id: str,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> bool:
    """更新任务状态。"""
    with _lock:
        tasks = _load_tasks(tasks_path)
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = status
                if result is not None:
                    task["result"] = result
                if error is not None:
                    task["error"] = error
                if status in ("completed", "failed"):
                    task["completed_at"] = datetime.now(CN_TZ).isoformat()
                _save_tasks(tasks, tasks_path)
                return True
    return False


def get_task(task_id: str, tasks_path: str = DEFAULT_TASKS_PATH) -> Optional[dict]:
    """获取单个任务。"""
    tasks = _load_tasks(tasks_path)
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


def get_latest_completed(tasks_path: str = DEFAULT_TASKS_PATH) -> Optional[dict]:
    """获取最近完成的任务。"""
    tasks = _load_tasks(tasks_path)
    completed = [t for t in tasks if t["status"] == "completed"]
    if not completed:
        return None
    completed.sort(key=lambda t: t.get("completed_at", ""), reverse=True)
    return completed[0]


def get_latest_in_progress(tasks_path: str = DEFAULT_TASKS_PATH) -> Optional[dict]:
    """获取最近待处理或执行中的任务。"""
    tasks = _load_tasks(tasks_path)
    active = [t for t in tasks if t["status"] in ("pending", "running")]
    if not active:
        return None
    active.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return active[0]


def list_tasks(
    status_filter: Optional[str] = None,
    tasks_path: str = DEFAULT_TASKS_PATH,
) -> list[dict]:
    """列出任务，可按状态筛选。"""
    tasks = _load_tasks(tasks_path)
    if status_filter:
        tasks = [t for t in tasks if t["status"] == status_filter]
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return tasks


def get_pending_tasks(tasks_path: str = DEFAULT_TASKS_PATH) -> list[dict]:
    """获取所有待处理的任务。"""
    return list_tasks("pending", tasks_path)


def get_running_tasks(tasks_path: str = DEFAULT_TASKS_PATH) -> list[dict]:
    """获取所有执行中的任务。"""
    return list_tasks("running", tasks_path)
