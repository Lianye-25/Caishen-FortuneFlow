"""
财神上下左右 — 消息分发引擎

用法：
    from dispatcher import dispatch
    result = dispatch(parse_result, contacts, config)

纯标准库实现，零外部依赖。支持邮件通道，微信预留。
"""

import json
import os
import smtplib
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# 中国时区
CN_TZ = timezone(timedelta(hours=8))

# 需要分发的方向
DISPATCHABLE_DIRECTIONS = {"UP", "DOWN"}

# 方向→中文标签
DIRECTION_LABEL = {
    "UP": "汇报",
    "DOWN": "任务委派",
}

# 电话通知模板：单向通知，禁止闲聊
NOTIFY_TEMPLATE = (
    "【角色】你是电话通知员，不是闲聊朋友。禁止寒暄、禁止反问、禁止聊天。\n"
    "【任务】接通后立即用自然口语告知对方以下内容，说完即挂断，不要说多余的话：\n"
    "【通知内容】{content}"
)

# 电话询问模板：双向沟通，收集答复
INQUIRY_TEMPLATE = (
    "【角色】你是电话沟通助手，代表用户进行礼貌的询问沟通。\n"
    "【任务】接通后用自然口语向对方询问以下问题，认真听取对方的答复，"
    "对方回答后复述确认并礼貌结束通话。禁止闲聊其他话题。\n"
    "【询问内容】{content}"
)


def load_config(config_path: str) -> dict:
    """加载 config.json，不存在时返回空配置。"""
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def dispatch(parse_result: dict, contacts: dict, config: dict) -> dict:
    """
    根据意图解析结果执行消息分发。

    Args:
        parse_result: intent_parser.parse_intent() 的输出
        contacts: 联系人字典（superiors, subordinates, agents）
        config: config.json 内容

    Returns:
        分发结果字典
    """
    direction = parse_result.get("direction", "CENTER")
    target = parse_result.get("target")
    content = parse_result.get("content")
    confidence = parse_result.get("confidence", 0)

    # LEFT：子操作分发
    if direction == "LEFT":
        meta = parse_result.get("parse_metadata", {})
        sub_action = meta.get("left_sub_action", "archive_task")

        if sub_action == "complete_task":
            # finger_count=1：标记最近任务为完成
            from task_manager import get_latest_in_progress, update_task
            latest = get_latest_in_progress()
            if latest:
                update_task(latest["id"], "completed")
                return {
                    "status": "success",
                    "reason": f"任务 {latest['id']} 已标记为完成",
                    "completed_task": {
                        "id": latest["id"],
                        "target_name": latest.get("target_name"),
                        "content": latest.get("content"),
                    },
                    "channels_dispatched": [],
                    "results": [],
                }
            return {
                "status": "skipped",
                "reason": "没有进行中的任务",
                "channels_dispatched": [],
                "results": [],
            }

        elif sub_action == "archive_task":
            # finger_count=2：归档已完成的任务
            from task_manager import get_latest_completed, update_task
            latest = get_latest_completed()
            if latest:
                update_task(latest["id"], "archived")
                return {
                    "status": "success",
                    "reason": f"任务 {latest['id']} 已归档",
                    "archived_task": {
                        "id": latest["id"],
                        "target_name": latest.get("target_name"),
                        "content": latest.get("content"),
                    },
                    "channels_dispatched": [],
                    "results": [],
                }
            return {
                "status": "skipped",
                "reason": "没有待归档的已完成任务",
                "channels_dispatched": [],
                "results": [],
            }

    # CENTER 无需分发
    if direction == "CENTER":
        return {
            "status": "skipped",
            "reason": "CENTER 方向无需消息分发",
            "channels_dispatched": [],
            "results": [],
        }

    # RIGHT：异步 Agent 执行
    if direction == "RIGHT":
        llm_config = config.get("llm", {})
        if not llm_config or not llm_config.get("api_key"):
            return {
                "status": "failed",
                "reason": "LLM API key 未配置，无法执行 Agent 任务",
                "channels_dispatched": [],
                "results": [],
            }

        target_name = target.get("name", "未知Agent") if target else "通用Agent"

        from task_manager import create_task
        from agent_runner import run_agent_async

        task_id = create_task(direction, target_name, content)
        thread = run_agent_async(task_id, target_name, content, llm_config)

        return {
            "status": "running",
            "reason": f"Agent 任务已后台启动",
            "task_id": task_id,
            "target_name": target_name,
            "channels_dispatched": ["agent"],
            "results": [
                {
                    "channel": "agent",
                    "status": "running",
                    "task_id": task_id,
                    "target": target_name,
                }
            ],
        }

    # UP / DOWN：需要目标联系人
    if not target:
        return {
            "status": "failed",
            "reason": "未匹配到目标联系人，无法分发",
            "channels_dispatched": [],
            "results": [],
        }

    target_name = target.get("name", "")
    target_channels = target.get("channels", [])
    target_address = target.get("address", "")

    # DOWN 方向：创建任务记录，生成 task_id 供后续下属回复匹配
    task_id = None
    if direction == "DOWN":
        from task_manager import create_task
        task_id = create_task(direction, target_name, content)

    if not target_channels:
        return {
            "status": "failed",
            "reason": f"联系人 {target_name} 未配置分发通道",
            "channels_dispatched": [],
            "results": [],
        }

    results = []
    channels_dispatched = []
    channels_skipped = []

    preferred_channel = parse_result.get("preferred_channel")

    for channel in target_channels:
        # 用户指定了通道 → 只走指定通道
        if preferred_channel and channel != preferred_channel:
            channels_skipped.append({
                "channel": channel,
                "reason": f"用户指定了{preferred_channel}通道，跳过{channel}"
            })
            continue

        if channel == "email":
            email_config = config.get("email", {})
            if not email_config or not email_config.get("username"):
                channels_skipped.append({"channel": "email", "reason": "SMTP 未配置"})
                continue
            if not target_address:
                channels_skipped.append({"channel": "email", "reason": f"{target_name} 未填写邮箱地址"})
                continue

            try:
                _send_email(
                    to_address=target_address,
                    to_name=target_name,
                    direction=direction,
                    content=content,
                    config=email_config,
                    task_id=task_id,
                )
                results.append({"channel": "email", "status": "sent", "to": target_address})
                channels_dispatched.append("email")
            except Exception as e:
                results.append({"channel": "email", "status": "failed", "to": target_address, "error": str(e)})
                channels_skipped.append({"channel": "email", "reason": str(e)})

        elif channel == "phone":
            voice_config = config.get("voice_call", {})
            if not voice_config or not voice_config.get("stepone_api_key"):
                channels_skipped.append({"channel": "phone", "reason": "Stepone AI API Key 未配置"})
                continue
            target_phone = target.get("phone", "")
            if not target_phone:
                channels_skipped.append({"channel": "phone", "reason": f"{target_name} 未填写电话号码"})
                continue

            try:
                import subprocess
                env = os.environ.copy()
                env["STEPONEAI_API_KEY"] = voice_config["stepone_api_key"]
                raw_content = content if content else "新通知"
                call_mode = parse_result.get("call_mode", "notify")
                call_content = _wrap_phone_content(raw_content, voice_config, call_mode)
                result = subprocess.run(
                    ["stepone-call", target_phone, call_content],
                    capture_output=True, text=True, timeout=60, env=env
                )
                if result.returncode == 0:
                    call_id = result.stdout.strip().split()[-1] if result.stdout.strip() else None
                    results.append({"channel": "phone", "status": "sent", "to": target_phone,
                                   "call_id": call_id})
                    channels_dispatched.append("phone")
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip() or "拨打失败"
                    channels_skipped.append({"channel": "phone", "reason": error_msg})
            except FileNotFoundError:
                channels_skipped.append({"channel": "phone",
                                        "reason": "stepone-call CLI 未安装，请运行 npm install -g openclaw-ai-calls-china-phone"})
            except subprocess.TimeoutExpired:
                channels_skipped.append({"channel": "phone", "reason": "stepone-call 执行超时"})
            except Exception as e:
                results.append({"channel": "phone", "status": "failed", "to": target_phone, "error": str(e)})
                channels_skipped.append({"channel": "phone", "reason": str(e)})

        elif channel == "wechat":
            wechat_config = config.get("channels", {}).get("wechat", {})
            if not wechat_config.get("enabled", False):
                channels_skipped.append({"channel": "wechat", "reason": "未启用"})
                continue
            if not all([wechat_config.get("corp_id"), wechat_config.get("agent_id"), wechat_config.get("secret")]):
                channels_skipped.append({"channel": "wechat", "reason": "企业微信配置不完整（需 corp_id / agent_id / secret）"})
                continue
            target_userid = target.get("wechat_userid", "")
            if not target_userid:
                channels_skipped.append({"channel": "wechat", "reason": f"{target_name} 未填写 wechat_userid"})
                continue

            try:
                token = _get_wechat_access_token(
                    wechat_config["corp_id"],
                    wechat_config["secret"]
                )
                if not token:
                    channels_skipped.append({"channel": "wechat", "reason": "获取企业微信 access_token 失败"})
                    continue
                _send_wechat_message(token, wechat_config["agent_id"], target_userid, direction, content)
                results.append({"channel": "wechat", "status": "sent", "to": target_userid})
                channels_dispatched.append("wechat")
            except Exception as e:
                results.append({"channel": "wechat", "status": "failed", "to": target_userid, "error": str(e)})
                channels_skipped.append({"channel": "wechat", "reason": str(e)})

    # 汇总状态
    if channels_dispatched:
        if channels_skipped:
            status = "partial"
        else:
            status = "success"
    else:
        if channels_skipped:
            status = "failed"
        else:
            status = "skipped"

    result = {
        "status": status,
        "channels_available": target_channels,
        "channels_dispatched": channels_dispatched,
        "channels_skipped": channels_skipped,
        "results": results,
    }
    if task_id:
        result["task_id"] = task_id
    return result


def _wrap_phone_content(content: str, voice_config: dict, call_mode: str = "notify") -> str:
    """根据电话模式包装内容模板。

    call_mode: "notify" → 通知模板, "inquiry" → 询问模板
    voice_config.notify_mode=false 时跳过包装。
    """
    if not voice_config.get("notify_mode", True):
        return content
    if call_mode == "inquiry":
        return INQUIRY_TEMPLATE.format(content=content)
    return NOTIFY_TEMPLATE.format(content=content)


def _send_email(
    to_address: str,
    to_name: str,
    direction: str,
    content: Optional[str],
    config: dict,
    task_id: Optional[str] = None,
) -> None:
    """通过 SMTP 发送邮件。"""
    smtp_server = config.get("smtp_server", "smtp.qq.com")
    smtp_port = config.get("smtp_port", 587)
    use_tls = config.get("use_tls", True)
    username = config.get("username", "")
    password = config.get("password", "")
    from_name = config.get("from_name", "财神上下左右")

    subject, body_html = _render_email(to_name, direction, content, task_id)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{username}>"
    msg["To"] = f"{to_name} <{to_address}>"
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
    try:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.sendmail(username, to_address, msg.as_string())
    finally:
        server.quit()


def _render_email(to_name: str, direction: str, content: Optional[str], task_id: Optional[str] = None) -> tuple[str, str]:
    """根据方向渲染邮件主题和 HTML 正文。DOWN 委派时主题带 task_id 供下属回复匹配。"""
    label = DIRECTION_LABEL.get(direction, "通知")
    content_text = content if content else "（无具体内容）"
    now_str = datetime.now(CN_TZ).strftime("%Y年%m月%d日 %H:%M")

    if direction == "UP":
        subject = f"【财神 汇报】{content_text[:30]}"
        body_html = f"""\
<html><body>
<h2>财神上下左右 — 汇报</h2>
<p><strong>{to_name}，您好：</strong></p>
<p>以下为汇报内容：</p>
<blockquote style="background:#f5f5f5;padding:12px;border-left:4px solid #4A90D9;">
{content_text}
</blockquote>
<p style="color:#888;font-size:12px;">发送时间：{now_str}</p>
<hr>
<p style="color:#aaa;font-size:11px;">此邮件由 财神上下左右自动发送</p>
</body></html>"""
    else:
        subject = f"【财神 任务委派】{content_text[:30]}"
        if task_id:
            subject = f"【财神 任务委派】{task_id} {content_text[:30]}"
        body_html = f"""\
<html><body>
<h2>财神上下左右 — 任务委派</h2>
<p><strong>{to_name}，您好：</strong></p>
<p>请您处理以下任务：</p>
<blockquote style="background:#f5f5f5;padding:12px;border-left:4px solid #E8A838;">
{content_text}
</blockquote>
<p style="color:#888;font-size:12px;">委派时间：{now_str}</p>
<hr>
<p style="color:#aaa;font-size:11px;">此邮件由 财神上下左右自动发送</p>
</body></html>"""

    return subject, body_html


# ============================================================
# 反馈通知：任务完成后自动通知用户（contacts.self）
# ============================================================

def send_feedback(task_info: dict, contacts: dict, config: dict) -> dict:
    """
    向用户（contacts.self）发送任务完成反馈通知。
    复用现有邮件/企微/电话通道，接收方为 self 配置的通道。

    Args:
        task_info: 任务字典（来自 task_manager）
        contacts: 联系人字典（需包含 self 字段）
        config: config.json 内容

    Returns:
        分发结果字典
    """
    self_contact = contacts.get("self")
    if not self_contact:
        return {"status": "skipped", "reason": "contacts.json 中未配置 self"}

    self_channels = self_contact.get("channels", [])
    if not self_channels:
        return {"status": "skipped", "reason": "self 未配置接收通道"}

    target_name = task_info.get("target_name", "未知")
    content = task_info.get("content", "") or ""
    direction = task_info.get("direction", "")

    dir_label = {"UP": "汇报", "DOWN": "委派", "RIGHT": "Agent执行"}.get(direction, "任务")
    feedback_content = f"{target_name}已完成{dir_label}「{content}」"

    results = []
    channels_dispatched = []

    for channel in self_channels:
        if channel == "email":
            email_config = config.get("email", {})
            self_address = self_contact.get("address", "")
            if not email_config.get("username") or not self_address:
                results.append({"channel": "email", "status": "skipped", "reason": "邮箱未配置"})
                continue
            try:
                _send_feedback_email(self_address, feedback_content, target_name, email_config)
                results.append({"channel": "email", "status": "sent", "to": self_address})
                channels_dispatched.append("email")
            except Exception as e:
                results.append({"channel": "email", "status": "failed", "error": str(e)})

        elif channel == "wechat":
            wechat_config = config.get("channels", {}).get("wechat", {})
            self_userid = self_contact.get("wechat_userid", "")
            if not wechat_config.get("enabled") or not self_userid:
                results.append({"channel": "wechat", "status": "skipped", "reason": "企微未配置"})
                continue
            try:
                token = _get_wechat_access_token(
                    wechat_config.get("corp_id", ""), wechat_config.get("secret", "")
                )
                if not token:
                    results.append({"channel": "wechat", "status": "failed", "reason": "获取 access_token 失败"})
                    continue
                _send_wechat_feedback(token, wechat_config.get("agent_id"), self_userid, feedback_content)
                results.append({"channel": "wechat", "status": "sent", "to": self_userid})
                channels_dispatched.append("wechat")
            except Exception as e:
                results.append({"channel": "wechat", "status": "failed", "error": str(e)})

        elif channel == "phone":
            voice_config = config.get("voice_call", {})
            self_phone = self_contact.get("phone", "")
            if not voice_config.get("stepone_api_key") or not self_phone:
                results.append({"channel": "phone", "status": "skipped", "reason": "电话未配置"})
                continue
            try:
                import subprocess
                env = os.environ.copy()
                env["STEPONEAI_API_KEY"] = voice_config["stepone_api_key"]
                call_content = _wrap_phone_content(
                    f"任务完成通知：{feedback_content}", voice_config, "notify"
                )
                subprocess.run(
                    ["stepone-call", self_phone, call_content],
                    capture_output=True, text=True, timeout=60, env=env
                )
                results.append({"channel": "phone", "status": "sent", "to": self_phone})
                channels_dispatched.append("phone")
            except Exception as e:
                results.append({"channel": "phone", "status": "failed", "error": str(e)})

    status = "success" if channels_dispatched else "skipped"
    return {
        "status": status,
        "channels_dispatched": channels_dispatched,
        "results": results,
        "feedback_content": feedback_content,
    }


def _send_feedback_email(to_address, feedback_content, target_name, config):
    """发送任务完成反馈邮件给用户。"""
    smtp_server = config.get("smtp_server", "smtp.qq.com")
    smtp_port = config.get("smtp_port", 587)
    use_tls = config.get("use_tls", True)
    username = config.get("username", "")
    password = config.get("password", "")
    from_name = config.get("from_name", "财神上下左右")

    now_str = datetime.now(CN_TZ).strftime("%Y年%m月%d日 %H:%M")
    subject = f"【财神 任务完成】{target_name}"

    body_html = f"""\
<html><body>
<h2>财神上下左右 — 任务完成通知</h2>
<p><strong>您好：</strong></p>
<p>{feedback_content}</p>
<blockquote style="background:#f5f5f5;padding:12px;border-left:4px solid #4CAF50;">
完成时间：{now_str}
</blockquote>
<hr>
<p style="color:#aaa;font-size:11px;">此通知由 财神上下左右自动发送</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{username}>"
    msg["To"] = f"{to_address}"
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
    try:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.sendmail(username, to_address, msg.as_string())
    finally:
        server.quit()


def _send_wechat_feedback(token, agent_id, to_user, feedback_content):
    """发送任务完成反馈到企业微信。"""
    body = {
        "touser": to_user,
        "msgtype": "textcard",
        "agentid": agent_id,
        "textcard": {
            "title": "任务完成 — 财神",
            "description": feedback_content[:500],
            "url": "",
            "btntxt": "",
        },
    }
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode") != 0:
        raise RuntimeError(result.get("errmsg", "企业微信发送失败"))


# ============================================================
# 企业微信通道
# ============================================================

_WECHAT_TOKEN_CACHE = {"token": None, "expires_at": 0}


def _get_wechat_access_token(corp_id: str, secret: str) -> Optional[str]:
    """获取企业微信 access_token，带缓存（提前5分钟刷新）。"""
    now = time.time()
    if _WECHAT_TOKEN_CACHE["token"] and now < _WECHAT_TOKEN_CACHE["expires_at"] - 300:
        return _WECHAT_TOKEN_CACHE["token"]

    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errcode") == 0:
            _WECHAT_TOKEN_CACHE["token"] = data["access_token"]
            _WECHAT_TOKEN_CACHE["expires_at"] = now + data.get("expires_in", 7200)
            return _WECHAT_TOKEN_CACHE["token"]
    except Exception:
        pass
    return None


def _send_wechat_message(
    token: str,
    agent_id: int,
    to_user: str,
    direction: str,
    content: str,
) -> None:
    """通过企业微信应用发送 textcard 卡片消息。"""
    dir_label = {"UP": "汇报", "DOWN": "任务委派"}.get(direction, "通知")
    desc = (content or "（无内容）")[:500]

    body = {
        "touser": to_user,
        "msgtype": "textcard",
        "agentid": agent_id,
        "textcard": {
            "title": f"{dir_label} — 财神",
            "description": desc,
            "url": "",
            "btntxt": "",
        },
    }

    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode") != 0:
        raise RuntimeError(result.get("errmsg", "企业微信发送失败"))


# ============================================================
# CLI 入口（独立使用 dispatcher 时）
# ============================================================

def main():
    import argparse
    import sys

    # Windows UTF-8
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="财神上下左右 — 消息分发引擎")
    parser.add_argument("--intent", required=True, help="意图解析结果 JSON 文件路径（或 JSON 字符串）")
    parser.add_argument("--contacts", default=None, help="contacts.json 路径")
    parser.add_argument("--config", default=None, help="config.json 路径")

    args = parser.parse_args()

    # 加载意图
    intent_path = args.intent
    if os.path.exists(intent_path):
        with open(intent_path, "r", encoding="utf-8") as f:
            parse_result = json.load(f)
    else:
        parse_result = json.loads(intent_path)

    # 加载联系人
    if args.contacts:
        contacts_path = args.contacts
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        contacts_path = os.path.join(script_dir, "..", "assets", "contacts.json")
        contacts_path = os.path.normpath(contacts_path)

    from contact_matcher import load_contacts
    contacts = load_contacts(contacts_path)

    # 加载配置
    if args.config:
        config_path = args.config
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "..", "assets", "config.json")
        config_path = os.path.normpath(config_path)

    config = load_config(config_path)

    result = dispatch(parse_result, contacts, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
