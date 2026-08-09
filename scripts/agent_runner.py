"""
财神上下左右 — Agent 执行引擎

动态生成 System Prompt，通过 DeepSeek API 执行 Agent 任务。
纯标准库实现（urllib + json），后台线程异步执行。
"""

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional

# Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from task_manager import update_task


def run_agent(
    task_id: str,
    target_name: str,
    content: Optional[str],
    config: dict,
    tasks_path: Optional[str] = None,
) -> None:
    """
    在后台线程中执行 Agent 任务。
    完成后自动更新任务状态（completed / failed）。
    """
    try:
        update_task(task_id, "running", tasks_path=tasks_path)

        result = _call_llm(target_name, content, config)

        update_task(task_id, "completed", result=result, tasks_path=tasks_path)
    except Exception as e:
        update_task(task_id, "failed", error=str(e), tasks_path=tasks_path)


def _call_llm(target_name: str, content: Optional[str], config: dict) -> str:
    """调用 LLM API 执行 Agent 任务。"""
    api_key = config.get("api_key", "")
    api_base = config.get("api_base", "https://api.deepseek.com/v1").rstrip("/")
    model = config.get("model", "deepseek-chat")
    max_tokens = config.get("max_tokens", 4096)
    temperature = config.get("temperature", 0.7)

    system_prompt = _build_system_prompt(target_name)
    user_content = content if content else "请开始执行任务"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    url = f"{api_base}/chat/completions"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API 请求失败 (HTTP {e.code}): {error_body}") from e

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"API 返回为空: {json.dumps(data, ensure_ascii=False)}")

    return choices[0].get("message", {}).get("content", "")


def _build_system_prompt(target_name: str) -> str:
    """根据 Agent 名称动态生成 System Prompt。"""
    name = target_name.replace("Agent", "").replace("agent", "").strip()

    return (
        f"你是一个专业的{name}。\n"
        f"用户会给你一个任务，请你认真完成并返回结果。\n"
        f"请用中文回复。如果需要生成代码，请确保代码正确且可运行。"
    )


def run_agent_async(
    task_id: str,
    target_name: str,
    content: Optional[str],
    config: dict,
    tasks_path: Optional[str] = None,
):
    """启动独立子进程执行 Agent 任务，主进程退出后子进程继续运行。"""
    import subprocess

    script_path = os.path.abspath(__file__)
    if tasks_path is None:
        from task_manager import DEFAULT_TASKS_PATH
        tasks_path = DEFAULT_TASKS_PATH

    # 将 config 写入临时文件传递给子进程
    config_json = json.dumps(config, ensure_ascii=False)
    content_json = json.dumps(content if content else "", ensure_ascii=False)

    subprocess.Popen(
        [
            sys.executable, script_path,
            "--task-id", task_id,
            "--target-name", target_name,
            "--content", content_json,
            "--config", config_json,
            "--tasks-path", tasks_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


# ============================================================
# CLI 入口（子进程模式）
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="财神 Agent 执行器")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--content", default="")
    parser.add_argument("--config", required=True)
    parser.add_argument("--tasks-path", required=True)
    args = parser.parse_args()

    config = json.loads(args.config)
    content = json.loads(args.content) if args.content else None

    run_agent(args.task_id, args.target_name, content, config, args.tasks_path)


if __name__ == "__main__":
    main()
