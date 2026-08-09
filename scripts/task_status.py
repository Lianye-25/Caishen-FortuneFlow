"""
财神上下左右 — 任务状态查询 CLI

供小智/OpenClaw 轮询任务状态使用。

用法：
    python task_status.py --pending          # 查询待处理任务
    python task_status.py --running          # 查询执行中任务
    python task_status.py --latest-completed # 查询最近完成的任务
    python task_status.py --archive task-xxx # 归档指定任务
    python task_status.py --list             # 列出所有任务
"""

import argparse
import json
import os
import sys

# Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from task_manager import (
    get_pending_tasks,
    get_running_tasks,
    get_latest_completed,
    list_tasks,
    update_task,
    get_task,
)


def main():
    parser = argparse.ArgumentParser(description="财神 任务状态查询")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pending", action="store_true", help="查询待处理任务")
    group.add_argument("--running", action="store_true", help="查询执行中任务")
    group.add_argument("--latest-completed", action="store_true", help="查询最近完成的任务")
    group.add_argument("--list", action="store_true", help="列出所有任务")
    group.add_argument("--archive", metavar="TASK_ID", help="归档指定任务")
    group.add_argument("--get", metavar="TASK_ID", help="查询指定任务详情")

    args = parser.parse_args()

    if args.pending:
        tasks = get_pending_tasks()
        result = {"pending_count": len(tasks), "tasks": tasks}
    elif args.running:
        tasks = get_running_tasks()
        result = {"running_count": len(tasks), "tasks": tasks}
    elif args.latest_completed:
        task = get_latest_completed()
        if task:
            result = {"has_completed": True, "task": task}
        else:
            result = {"has_completed": False, "task": None}
    elif args.archive:
        success = update_task(args.archive, "archived")
        result = {"archived": success, "task_id": args.archive}
    elif args.get:
        task = get_task(args.get)
        result = {"task": task}
    elif args.list:
        tasks = list_tasks()
        result = {"total": len(tasks), "tasks": tasks}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
