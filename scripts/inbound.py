"""
财神上下左右 — inbound 接收引擎

接收下属完成任务后的汇报，匹配任务、标记完成、通知用户。

支持三种 inbound 方式：
- 邮件回复（IMAP，完整实现，可跑通）
- 企业微信回调（框架 stub，待公网服务器）
- 电话接听（框架 stub，待接听+ASR）

用法：
    python inbound.py --check              # 检查一次收件箱
    python inbound.py --watch              # 定时轮询（默认 60 秒）
    python inbound.py --watch --interval 30
"""

import argparse
import email
import imaplib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from typing import Optional

# Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

CN_TZ = timezone(timedelta(hours=8))

# task_id 格式：task-YYYYMMDDHHMMSS-ffffff
TASK_ID_PATTERN = re.compile(r'task-\d{14}-\d{6}')


def _get_default_paths():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    contacts_path = os.path.normpath(os.path.join(script_dir, "..", "assets", "contacts.json"))
    config_path = os.path.normpath(os.path.join(script_dir, "..", "assets", "config.json"))
    tasks_path = os.path.normpath(os.path.join(script_dir, "..", "assets", "tasks.json"))
    return contacts_path, config_path, tasks_path


# ============================================================
# 邮件 IMAP 接收（完整实现）
# ============================================================

def _decode_mime_header(header: Optional[str]) -> str:
    """解码 MIME 编码的邮件头（主题/发件人）。"""
    if not header:
        return ""
    parts = decode_header(header)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_sender_email(msg) -> str:
    """从邮件头提取发件人邮箱地址。"""
    from_addr = msg.get("From", "")
    match = re.search(r'<([^>]+)>', from_addr)
    if match:
        return match.group(1).strip().lower()
    return from_addr.strip().lower()


def _extract_task_id(subject: str) -> Optional[str]:
    """从邮件主题提取 task_id。"""
    match = TASK_ID_PATTERN.search(subject)
    return match.group(0) if match else None


def _match_by_sender(sender_email: str, contacts: dict, tasks_path: str) -> Optional[dict]:
    """按发件人邮箱匹配下属，返回该下属最近的进行中任务。"""
    from task_manager import list_tasks
    for sub in contacts.get("subordinates", []):
        if (sub.get("address", "") or "").lower() == sender_email:
            tasks = list_tasks(tasks_path=tasks_path)
            for task in tasks:
                if (task.get("target_name") == sub.get("name")
                        and task.get("status") in ("pending", "running")):
                    return task
            break
    return None


def check_email_replies(config: dict, contacts: dict, tasks_path: str) -> dict:
    """
    检查收件箱，解析下属回复，匹配任务，标记完成，触发反馈。

    Args:
        config: config.json 内容
        contacts: 联系人字典
        tasks_path: tasks.json 路径

    Returns:
        处理结果字典
    """
    from task_manager import get_task, update_task
    from dispatcher import send_feedback

    inbound_config = config.get("inbound", {}).get("email", {})
    if not inbound_config.get("enabled"):
        return {"status": "skipped", "reason": "inbound.email 未启用（enabled=false）"}

    imap_server = inbound_config.get("imap_server", "imap.qq.com")
    imap_port = inbound_config.get("imap_port", 993)
    username = inbound_config.get("username", "")
    password = inbound_config.get("password", "")

    if not username or not password:
        return {"status": "failed", "reason": "IMAP 账号密码未配置"}

    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(username, password)
        mail.select("INBOX")
    except Exception as e:
        return {"status": "failed", "reason": f"IMAP 连接失败: {e}"}

    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        mail.logout()
        return {"status": "failed", "reason": "搜索未读邮件失败"}

    results = []
    for num in data[0].split():
        try:
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_mime_header(msg.get("Subject", ""))
            task_id = _extract_task_id(subject)

            # 主路径：task_id 匹配；备路径：发件人匹配
            task = None
            matched_by = None
            if task_id:
                task = get_task(task_id, tasks_path)
                if task and task.get("status") in ("pending", "running"):
                    matched_by = "task_id"
                else:
                    task = None
            if task is None:
                sender = _extract_sender_email(msg)
                task = _match_by_sender(sender, contacts, tasks_path)
                matched_by = "sender" if task else None

            if task:
                update_task(task["id"], "completed", tasks_path=tasks_path)
                feedback = send_feedback(task, contacts, config)
                results.append({
                    "task_id": task["id"],
                    "target_name": task.get("target_name"),
                    "matched_by": matched_by,
                    "feedback": feedback,
                })
                mail.store(num, "+FLAGS", "\\Seen")

        except Exception as e:
            results.append({"error": f"处理邮件失败: {e}"})

    mail.logout()
    return {
        "status": "success",
        "matched": sum(1 for r in results if "task_id" in r),
        "results": results,
    }


# ============================================================
# 企业微信回调（框架 stub）
# ============================================================

def handle_wechat_callback(xml_data: str) -> dict:
    """
    企业微信回调入口（框架 stub）。

    接收下属回复的消息，解析 task_id，匹配任务，标记完成，触发反馈。

    待接入：
    1. 部署公网回调服务器（本地运行无法接收企微回调）
    2. 在企业微信后台配置回调 URL + Token + AES Key
    3. 解析回调 XML（touser/fromuser/content）
    4. 提取 task_id → 匹配任务 → send_feedback
    """
    # TODO: 解析企业微信回调 XML
    # TODO: 提取 task_id（消息内容或来源消息主题）
    # TODO: get_task(task_id) → update_task(completed) → send_feedback
    raise NotImplementedError(
        "企微回调需要公网服务器，框架已就绪，待接入。"
        "配置见 config.json 的 inbound.wechat。"
    )


# ============================================================
# 电话接听（框架 stub）
# ============================================================

def handle_phone_inbound(call_data: dict) -> dict:
    """
    电话接听入口（框架 stub）。

    接收下属回拨，ASR 转文字，匹配任务，标记完成，触发反馈。

    待接入：
    1. 电话接听能力（当前 Stepone AI 主要支持外呼）
    2. 语音识别 ASR 将通话转文字
    3. 提取 task_id 或按来电号码匹配下属
    4. get_task(task_id) → update_task(completed) → send_feedback
    """
    # TODO: 接听电话 + ASR 转文字
    # TODO: 提取 task_id 或按来电号码匹配下属
    # TODO: get_task(task_id) → update_task(completed) → send_feedback
    raise NotImplementedError(
        "电话接听需要接听+ASR能力，框架已就绪，待接入。"
        "配置见 config.json 的 inbound.phone。"
    )


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="财神 inbound 接收引擎")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="检查一次收件箱")
    group.add_argument("--watch", action="store_true", help="定时轮询收件箱")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔秒数（默认 60）")

    args = parser.parse_args()

    contacts_path, config_path, tasks_path = _get_default_paths()

    from contact_matcher import load_contacts
    from dispatcher import load_config

    contacts = load_contacts(contacts_path)
    config = load_config(config_path)

    if args.check:
        result = check_email_replies(config, contacts, tasks_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.watch:
        print(f"开始轮询收件箱，间隔 {args.interval} 秒...")
        while True:
            try:
                result = check_email_replies(config, contacts, tasks_path)
                if result.get("matched"):
                    print(f"[{datetime.now(CN_TZ).strftime('%H:%M:%S')}] "
                          f"匹配到 {result['matched']} 个任务完成")
            except Exception as e:
                print(f"[{datetime.now(CN_TZ).strftime('%H:%M:%S')}] 错误: {e}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
