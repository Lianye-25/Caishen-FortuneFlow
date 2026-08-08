"""
HANDSFREE 五维中枢 — 意图解析引擎

用法：
    python intent_parser.py "向上汇报给张总今天的项目进展"
    python intent_parser.py "向下分派给小王整理会议纪要" --contacts path/to/contacts.json

输出：结构化 JSON 到 stdout
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# 中国时区
CN_TZ = timezone(timedelta(hours=8))

from contact_matcher import load_contacts, match_in_list

# ============================================================
# 方向关键词定义（按扫描优先级排列）
# ============================================================

DIRECTION_KEYWORDS = [
    ("UP", ["上报", "汇报", "提交", "报告", "告诉", "通知", "呈报", "报给", "发给", "反馈给"]),
    ("DOWN", ["分派", "委派", "分配", "交给", "让", "安排", "派给", "下发", "布置", "叫"]),
    ("LEFT", ["存档", "标记完成", "标记任务完成", "标记任务", "任务完成", "归档", "关闭任务", "标记为完成", "结束任务", "完成任务", "标记为"]),
    ("RIGHT", ["Agent处理", "agent处理", "AI处理", "智能处理", "机器处理", "自动处理"]),
]

DIRECTION_CN = {
    "UP": "上报",
    "DOWN": "委派",
    "LEFT": "存档",
    "RIGHT": "Agent分派",
    "CENTER": "中枢",
}

CONTACT_LIST_MAP = {
    "UP": "superiors",
    "DOWN": "subordinates",
    "RIGHT": "agents",
    "LEFT": None,
    "CENTER": None,
}

# 通道选择信号词（句首匹配，按长度降序以保证长词优先）
CHANNEL_KEYWORDS = [
    ("phone",  ["打电话", "打个电话", "电话通知", "电话告诉", "电话"]),
    ("email",  ["发邮件", "发个邮件", "邮件通知"]),
    ("wechat", ["发微信", "发个微信", "微信通知", "发消息", "发个消息"]),
]

# 电话模式信号词：区分通知/询问（在内容中扫描）
CALL_MODE_KEYWORDS = [
    ("inquiry", ["询问", "问一下", "问", "确认一下", "请问"]),
    ("notify",  ["通知", "告诉", "告知", "转告", "提醒"]),
]

# 中文名称后缀（职称/称谓）
TITLE_SUFFIXES = ["总", "经理", "总监", "工", "老师", "主管", "主任", "董", "老板", "哥", "姐"]

# 最大目标名称长度（中文字符）
MAX_TARGET_LENGTH = 6


def _detect_channel(text: str) -> tuple[Optional[str], str]:
    """检测句首通道选择信号词。返回 (preferred_channel, cleaned_text)。"""
    for channel, keywords in CHANNEL_KEYWORDS:
        for kw in sorted(keywords, key=len, reverse=True):
            if text.startswith(kw):
                remaining = text[len(kw):].strip()
                return (channel, remaining)
    return (None, text)


def _detect_call_mode(text: str) -> str:
    """检测电话模式：notify（默认）或 inquiry。"""
    for mode, keywords in CALL_MODE_KEYWORDS:
        for kw in sorted(keywords, key=len, reverse=True):
            if kw in text:
                return mode
    return "notify"  # 默认通知模式


def parse_intent(text: str, contacts: dict, gesture_context: dict | None = None) -> dict:
    """
    解析中文语音文本，提取五维意图。

    Args:
        text: 原始语音识别文本
        contacts: 联系人字典（superiors, subordinates, agents）
        gesture_context: 手势会话状态（direction + target），手势选人后语音说事时传入

    Returns:
        结构化意图 JSON
    """
    raw_input = text.strip()
    if not raw_input:
        return _make_center_result(raw_input, "输入为空")

    # 0. 通道信号词检测（句首优先）
    preferred_channel, clean_text = _detect_channel(raw_input)

    # 第一遍：关键词扫描
    matches = _scan_direction_keywords(clean_text)

    # 第二遍：上下文消歧
    direction, direction_keyword, ambiguities = _disambiguate(
        clean_text, matches, contacts
    )

    # 手势状态合并：方向+目标来自手势，内容来自语音（在早期返回之前合并）
    if gesture_context:
        direction = gesture_context["direction"]
        direction_keyword = None  # 方向来自手势，非文本关键词
        target = gesture_context.get("target")
        target_keyword = target.get("name", "") if target else None
    else:
        target = None
        target_keyword = None

    # 通道指定但无方向关键词时，从联系人列表反推方向
    if not direction and preferred_channel:
        for dir_candidate, list_key in [("DOWN", "subordinates"), ("UP", "superiors")]:
            contact_list = contacts.get(list_key, [])
            for contact in contact_list:
                name = contact.get("name", "")
                if name and name in clean_text:
                    direction = dir_candidate
                    direction_keyword = None
                    target = dict(contact)
                    target["match_type"] = "exact"
                    target["candidates"] = [name]
                    target_keyword = name
                    break
            if direction:
                break

    # 第三遍：优先级裁决
    if not direction:
        return _make_center_result(raw_input, "未检测到方向关键词", preferred_channel)

    # 提取目标（手势已提供则跳过）
    if not target:
        target_keyword, target = _extract_target(
            clean_text, direction, direction_keyword, contacts
        )

    # 提取内容（手势提供方向时，direction_keyword 为 None，直接取 clean_text）
    if direction_keyword is not None:
        content = _extract_content(clean_text, direction_keyword, target_keyword)
    else:
        content = clean_text if clean_text else None

    # 计算置信度
    confidence = _compute_confidence(direction, direction_keyword, target, content)

    result = {
        "direction": direction,
        "direction_cn": DIRECTION_CN[direction],
        "target": target,
        "content": content,
        "confidence": confidence,
        "raw_input": raw_input,
        "preferred_channel": preferred_channel,
        "call_mode": _detect_call_mode(raw_input) if preferred_channel == "phone" else None,
        "gesture_selected": gesture_context is not None,
        "parse_metadata": {
            "direction_keyword": direction_keyword,
            "target_keyword": target_keyword,
            "fuzzy_candidates": target.get("candidates", []) if target else [],
            "ambiguities": ambiguities,
        },
        "timestamp": datetime.now(CN_TZ).isoformat(),
    }

    return result


def build_intent_from_gesture(direction: str, finger_count: int, contacts: dict) -> dict:
    """
    从手势检测结果构建结构化意图 JSON，格式与 parse_intent() 一致。

    Args:
        direction: UP/DOWN/LEFT/RIGHT/CENTER
        finger_count: 1-4（手指数，用于选择联系人索引）
        contacts: 联系人字典（superiors, subordinates, agents）

    Returns:
        结构化意图 JSON，格式与 parse_intent() 输出一致
    """
    list_key = CONTACT_LIST_MAP.get(direction)
    contact_list = contacts.get(list_key, []) if list_key else []

    # 根据手指数选择联系人（1-based → 0-based索引）
    target = None
    target_keyword = None
    target_source = "gesture"

    if direction in ("LEFT", "CENTER"):
        # 不需要联系人
        pass
    elif contact_list and 1 <= finger_count <= len(contact_list):
        contact = contact_list[finger_count - 1]
        target = dict(contact)
        target["match_type"] = "gesture_index"
        target["candidates"] = [contact.get("name", "")]
        target_keyword = contact.get("name", "")

    # LEFT 子操作映射
    left_sub_action = None
    if direction == "LEFT":
        if finger_count == 1:
            left_sub_action = "complete_task"
        elif finger_count == 2:
            left_sub_action = "archive_task"

    # 置信度：手势识别结果直接映射，高置信度
    confidence = 0.9

    result = {
        "direction": direction,
        "direction_cn": DIRECTION_CN.get(direction, "中枢"),
        "target": target,
        "content": None,  # 手势场景下内容由后续语音提供
        "confidence": confidence,
        "raw_input": f"[gesture] {direction}({finger_count}指)",
        "preferred_channel": None,
        "parse_metadata": {
            "direction_keyword": None,
            "target_keyword": target_keyword,
            "fuzzy_candidates": target.get("candidates", []) if target else [],
            "ambiguities": [],
            "source": target_source,
            "left_sub_action": left_sub_action,
            "finger_count": finger_count,
        },
        "timestamp": datetime.now(CN_TZ).isoformat(),
    }

    return result


def _scan_direction_keywords(text: str) -> list[tuple[str, str, int]]:
    """
    第一遍扫描：找出所有方向关键词及其位置。
    返回 [(direction, keyword, position), ...] 按位置排序。
    """
    matches = []
    for direction, keywords in DIRECTION_KEYWORDS:
        for kw in keywords:
            pos = text.find(kw)
            if pos != -1:
                matches.append((direction, kw, pos))
    matches.sort(key=lambda x: x[2])
    return matches


def _disambiguate(
    text: str, matches: list[tuple[str, str, int]], contacts: dict
) -> tuple[Optional[str], Optional[str], list[str]]:
    """
    第二遍扫描：上下文消歧。

    关键逻辑：
    - "交给" + Agent → RIGHT
    - "交给" + 人名 → DOWN
    - "完成" 独立使用 → LEFT；含目标人物 → DOWN
    - 无匹配 → CENTER

    Returns:
        (direction, keyword, ambiguities)
    """
    if not matches:
        return (None, None, [])

    primary_dir, primary_kw, primary_pos = matches[0]
    ambiguities = [kw for d, kw, _ in matches[1:] if d != primary_dir]

    # 消歧规则1："交给" → 根据目标类型判断
    if primary_kw == "交给":
        target_name = _extract_name_after_keyword(text, primary_kw, primary_pos)
        if target_name:
            # 检查是否匹配 Agent
            if "Agent" in target_name or "agent" in target_name:
                return ("RIGHT", primary_kw, ambiguities)
            if contacts.get("agents"):
                for agent in contacts["agents"]:
                    if agent.get("name", "") == target_name:
                        return ("RIGHT", primary_kw, ambiguities)
            # 检查是否匹配下属
            if contacts.get("subordinates"):
                for sub in contacts["subordinates"]:
                    if sub.get("name", "") == target_name:
                        return ("DOWN", primary_kw, ambiguities)
            # 含 AI/Agent 字样 → RIGHT
            if "Agent" in text or "agent" in text or "AI" in text:
                return ("RIGHT", primary_kw, ambiguities)

    # 消歧规则2："完成" 独立 vs 含目标人物
    if primary_kw in ("完成", "完成任务"):
        # 检查"完成"后面是否跟着人名（含"让XX完成"模式）
        after_text = text[primary_pos + len(primary_kw):]
        # 模式：让/叫 XX 完成
        for delegate_kw in ["让", "叫", "交给", "分派给"]:
            if delegate_kw in text[:primary_pos]:
                # 前面的"让XX"说明是委派，不应归为 LEFT
                # 找最早的委派关键词
                for d, kw, pos in matches:
                    if d == "DOWN" and pos < primary_pos:
                        return (d, kw, [primary_kw] + [k for dd, k, _ in matches if dd != d and k != kw])

        # "完成"独立使用 → LEFT
        if not after_text.strip() or len(after_text.strip()) <= 10:
            return ("LEFT", primary_kw, ambiguities)

    # 消歧规则3："交给XX Agent处理" → 整体归 RIGHT
    if primary_dir == "DOWN" and primary_kw in ("交给", "让"):
        if "Agent" in text or "agent" in text or "AI" in text:
            # 检查后面是否有 Agent 关键词
            for d, kw, pos in matches:
                if d == "RIGHT" and pos > primary_pos:
                    return ("RIGHT", kw, [primary_kw] + ambiguities)

    # 消歧规则4："通知"/"告诉" → 根据目标人物所在列表确定方向
    if primary_kw in ("通知", "告诉"):
        # 在关键词附近搜索所有联系人的出现位置
        best_dir = None
        best_pos = len(text) + 1
        for sup in contacts.get("superiors", []):
            pos = text.find(sup.get("name", ""))
            if pos != -1 and pos < best_pos:
                best_pos = pos
                best_dir = "UP"
        for sub in contacts.get("subordinates", []):
            pos = text.find(sub.get("name", ""))
            if pos != -1 and pos < best_pos:
                best_pos = pos
                best_dir = "DOWN"
        if best_dir:
            return (best_dir, primary_kw, ambiguities)
        # 都未匹配 → 保持原方向（UP）

    return (primary_dir, primary_kw, ambiguities)


def _extract_name_after_keyword(text: str, keyword: str, pos: int) -> Optional[str]:
    """从关键词位置之后提取可能的人名/Agent名。

    采用长度候选法：从关键词后取 2~6 个字符作为候选名称，
    逐长度尝试匹配联系人，取最佳匹配。中文名称通常 2-4 字。
    """
    after = text[pos + len(keyword):].strip()

    # 跳过介词 "给" "为" "到" "向"
    for prep in ["给", "为", "到", "向"]:
        if after.startswith(prep):
            after = after[1:].strip()
            break

    if not after:
        return None

    # 取前若干字符作为名称候选区
    candidate_area = after[:MAX_TARGET_LENGTH]

    # 如果候选区包含明显的内容分隔词，截断
    for sep in ["的", "去", "做", "处理", "分析", "优化", "检查", "审查", "写", "整理", "完成"]:
        idx = candidate_area.find(sep)
        if idx > 1:  # 至少保留2个字符作为名称
            candidate_area = candidate_area[:idx]
            break

    # 去除尾部标点
    candidate_area = candidate_area.rstrip("，。：:、的了吧吗呢啊哦")

    return candidate_area.strip() if candidate_area.strip() else None


def _extract_target(
    text: str, direction: str, keyword: str, contacts: dict
) -> tuple[Optional[str], Optional[dict]]:
    """
    提取目标人物/Agent。

    在全文本中搜索联系人列表中的名称，取最接近关键词位置且匹配质量最高者。
    避免仅在关键词后搜索的问题（目标可能出现在关键词前）。

    Returns:
        (target_keyword, target_dict) — 无匹配时返回 (None, None)
    """
    list_key = CONTACT_LIST_MAP.get(direction)
    if not list_key:
        return (None, None)

    contact_list = contacts.get(list_key, [])
    if not contact_list:
        return (None, None)

    kw_pos = text.find(keyword)
    if kw_pos == -1:
        return (None, None)

    # 在全文本中搜索所有联系人的出现位置
    best_contact = None
    best_name = None
    best_dist = len(text) + 1  # 到关键词的距离

    for contact in contact_list:
        contact_name = contact.get("name", "")
        pos = text.find(contact_name)
        if pos != -1:
            dist = abs(pos - kw_pos)
            if dist < best_dist:
                best_dist = dist
                best_contact = dict(contact)
                best_contact["match_type"] = "exact"
                best_contact["candidates"] = [contact_name]
                best_name = contact_name

    if best_contact:
        return (best_name, best_contact)

    # 直接匹配失败，在关键词附近做模糊匹配
    after = text[kw_pos + len(keyword):].strip()
    for prep in ["给", "为", "到", "向"]:
        if after.startswith(prep):
            after = after[1:].strip()
            break

    if not after:
        return (None, None)

    for length in (4, 3, 2):
        if length > len(after):
            continue
        candidate = after[:length]
        # 跳过纯虚词候选
        if candidate in ("这个", "那个", "这份", "这些", "一下", "一个", "什么"):
            continue
        result = match_in_list(candidate, contact_list)
        if result.get("match_type") in ("exact", "fuzzy"):
            return (candidate, result)

    # RIGHT 方向：无预定义匹配时，尝试动态创建 Agent
    # 仅当关键词是委派型（交给/让）时才尝试，通用AI关键词（AI处理等）不提取目标
    if direction == "RIGHT" and keyword in ("交给", "让"):
        dynamic_name = _extract_dynamic_agent_name(text, keyword, kw_pos)
        if dynamic_name:
            return (dynamic_name, {
                "name": dynamic_name,
                "match_type": "dynamic",
                "candidates": [dynamic_name],
            })

    # 无匹配，不猜测
    return (None, None)


def _extract_dynamic_agent_name(text: str, keyword: str, kw_pos: int) -> Optional[str]:
    """RIGHT 方向无预定义匹配时，从文本中提取动态 Agent 名称。"""
    after = text[kw_pos + len(keyword):].strip()
    # 跳过介词
    for prep in ["给", "为", "到", "向"]:
        if after.startswith(prep):
            after = after[1:].strip()
            break

    if not after:
        return None

    # 优先在整个 after 中查找 "Agent" 关键词位置
    agent_pos = after.find("Agent")
    if agent_pos == -1:
        agent_pos = after.find("agent")

    if agent_pos > 0:
        # Agent 关键词之前是名称，包含 Agent 一起返回
        candidate_area = after[:agent_pos + 5]
    else:
        # 没有 Agent 关键词：在前 8 字符中截断到内容分隔词
        candidate_area = after[:8]
        for sep in ["处理", "检查", "分析", "优化", "审查", "翻译", "润色", "生成", "做", "的", "了", "把"]:
            idx = candidate_area.find(sep)
            if idx > 1:
                candidate_area = candidate_area[:idx]
                break

    candidate_area = candidate_area.rstrip("，。：:、的了吧吗呢啊哦把")
    if not candidate_area or len(candidate_area) < 2:
        return None

    # 确保包含 "Agent" 或 "agent" 关键词（RIGHT 方向特征）
    # 如果没有，尝试追加 "Agent" 后缀
    if "Agent" not in candidate_area and "agent" not in candidate_area:
        # 纯中文名称如 "数据分析" → "数据分析Agent"
        candidate_area = candidate_area + "Agent"

    return candidate_area.strip()


def _extract_content(text: str, direction_keyword: str, target_name: Optional[str]) -> Optional[str]:
    """
    提取内容负载：从原文中剥离方向关键词、目标名称和方向信号词后剩余的部分。
    """
    remaining = text

    # 移除目标名称（如果在文本中）
    if target_name and target_name in remaining:
        remaining = remaining.replace(target_name, "", 1)

    # 移除方向关键词（可能在移除目标后不再完整，尝试查找）
    kw_pos = remaining.find(direction_keyword)
    if kw_pos == -1:
        # 关键词可能被目标移除打断，尝试部分匹配
        for part in [direction_keyword, direction_keyword.replace("处理", "").replace("Agent", "").strip()]:
            if part:
                kw_pos = remaining.find(part)
                if kw_pos != -1:
                    break

    if kw_pos != -1:
        # 关键词可能在目标移除后已经部分缺失，移除关键词区域
        remaining = remaining[kw_pos + len(direction_keyword):]

    # 移除残留的方向信号词
    signal_words = ["让", "叫", "交给", "分派给", "汇报给", "上报给", "委派给", "安排", "通知"]
    for sw in sorted(signal_words, key=len, reverse=True):
        if remaining.startswith(sw):
            remaining = remaining[len(sw):]
            break

    # 移除介词
    for prep in ["给", "为", "到", "向"]:
        if remaining.startswith(prep):
            remaining = remaining[1:]
            break

    remaining = remaining.strip()

    # 移除前导标点
    for punct in ["的", "：", ":", "，", ",", "。"]:
        if remaining.startswith(punct):
            remaining = remaining[1:].strip()

    return remaining if remaining else None


def _compute_confidence(
    direction: str, keyword: Optional[str], target: Optional[dict], content: Optional[str]
) -> float:
    """计算置信度评分 (0.0 ~ 1.0)。"""
    # 方向得分
    if direction == "CENTER":
        direction_score = 0.3
    elif keyword:
        direction_score = 0.9
    else:
        direction_score = 0.6

    # 目标得分
    if direction in ("LEFT", "CENTER"):
        target_score = 0.3  # 不需要目标
    elif target and target.get("match_type") == "exact":
        target_score = 0.9
    elif target and target.get("match_type") == "fuzzy":
        target_score = 0.5
    elif target and target.get("match_type") == "none":
        target_score = 0.0
    else:
        target_score = 0.0

    # 内容得分
    if content and len(content) > 2:
        content_score = 0.9
    elif content:
        content_score = 0.6
    else:
        content_score = 0.4

    return round((direction_score + target_score + content_score) / 3, 2)


def _make_center_result(raw_input: str, reason: str, preferred_channel: Optional[str] = None) -> dict:
    """生成 CENTER（中枢）默认结果。"""
    return {
        "direction": "CENTER",
        "direction_cn": "中枢",
        "target": None,
        "content": raw_input if raw_input else None,
        "confidence": 0.3,
        "raw_input": raw_input,
        "preferred_channel": preferred_channel,
        "call_mode": _detect_call_mode(raw_input) if preferred_channel == "phone" else None,
        "gesture_selected": False,
        "parse_metadata": {
            "direction_keyword": None,
            "target_keyword": None,
            "fuzzy_candidates": [],
            "ambiguities": [],
            "note": reason,
        },
        "timestamp": datetime.now(CN_TZ).isoformat(),
    }


# ============================================================
# 手势会话状态管理（手势选人 → 语音说事）
# ============================================================

def _get_state_path() -> str:
    """获取手势状态文件路径。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "gesture_state.json")


def _save_gesture_state(direction: str, target: dict | None, finger_count: int):
    """保存手势选中状态，供后续语音合并。5分钟过期。"""
    import json as _json
    now = datetime.now(CN_TZ)
    state = {
        "direction": direction,
        "target": target,
        "finger_count": finger_count,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    state_path = _get_state_path()
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        _json.dump(state, f, ensure_ascii=False, indent=2)


def _load_gesture_state() -> dict | None:
    """加载手势状态，过期返回 None。"""
    import json as _json
    state_path = _get_state_path()
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = _json.load(f)
        expires_at = datetime.fromisoformat(state.get("expires_at", ""))
        if datetime.now(CN_TZ) > expires_at:
            _clear_gesture_state()
            return None
        return state
    except (OSError, ValueError, KeyError):
        return None


def _clear_gesture_state():
    """清除手势状态文件。"""
    state_path = _get_state_path()
    try:
        os.remove(state_path)
    except OSError:
        pass


def route(text: str, contacts: dict, llm_call=None) -> dict:
    """
    小智消息路由入口——自动区分摄像头控制、手势描述、语音指令。

    Args:
        text: 小智传来的原始文本
        contacts: 联系人字典
        llm_call: LLM 调用函数，签名 llm_call(prompt: str) -> str。
                  不传则跳过手势解析，仅做摄像头控制+语音。

    Returns:
        结构化结果。摄像头指令返回 {"action": "open_camera"/"close_camera"}，
        手势返回 build_intent_from_gesture() 结果，语音返回 parse_intent() 结果。
    """
    from xiaozhi_gesture_parser import is_camera_control, build_gesture_prompt, parse_llm_result

    # 1. 摄像头控制指令
    cam = is_camera_control(text)
    if cam == "open":
        return {"source": "gesture", "action": "open_camera", "led": "purple"}
    if cam == "close":
        _clear_gesture_state()
        return {"source": "gesture", "action": "close_camera", "led": "off"}

    # 1.5 检查是否有待处理的手势状态（手势选人 + 语音说事）
    pending_gesture = _load_gesture_state()

    # 2. 尝试手势解析（需要 LLM）
    if llm_call:
        prompt = build_gesture_prompt(text)
        llm_output = llm_call(prompt)
        gesture = parse_llm_result(llm_output)
        if gesture:
            result = build_intent_from_gesture(
                gesture["direction"], gesture["finger_count"], contacts
            )
            if result.get("target"):
                # 手势选中了联系人 → 保存状态，等待用户说话
                _save_gesture_state(
                    direction=result["direction"],
                    target=result["target"],
                    finger_count=gesture["finger_count"],
                )
                return {
                    "source": "gesture",
                    "action": "person_selected",
                    "direction": result["direction"],
                    "target_name": result["target"].get("name"),
                    "message": f"已选中{result['target'].get('name', '联系人')}，请说内容",
                }
            # LEFT/CENTER 不需要联系人
            return result

    # 3. 语音意图解析（可能合并手势状态）
    if pending_gesture:
        result = parse_intent(text, contacts, gesture_context=pending_gesture)
        _clear_gesture_state()
        return result

    return parse_intent(text, contacts)


def main():
    parser = argparse.ArgumentParser(
        description="HANDSFREE 五维中枢 — 意图解析引擎"
    )
    parser.add_argument("text", nargs="?", help="待解析的中文语音文本")
    parser.add_argument(
        "--contacts",
        default=None,
        help="contacts.json 路径（默认使用 assets/contacts.json）",
    )
    parser.add_argument(
        "--pretty", action="store_true", default=True, help="美化 JSON 输出（默认开启）"
    )
    parser.add_argument(
        "--dispatch", action="store_true", default=False, help="解析完成后自动执行消息分发"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="config.json 路径（默认使用 assets/config.json）",
    )

    args = parser.parse_args()

    if not args.text:
        parser.print_help()
        sys.exit(1)

    # 解析 contacts 路径
    if args.contacts:
        contacts_path = args.contacts
    else:
        # 默认路径：相对于脚本所在目录的 assets/contacts.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        contacts_path = os.path.join(script_dir, "..", "assets", "contacts.json")
        contacts_path = os.path.normpath(contacts_path)

    contacts = load_contacts(contacts_path)
    result = parse_intent(args.text, contacts)

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))

    # 如果指定了 --dispatch，执行分发
    if args.dispatch:
        # 解析 config 路径
        if args.config:
            config_path = args.config
        else:
            config_path = os.path.join(script_dir, "..", "assets", "config.json")
            config_path = os.path.normpath(config_path)

        from dispatcher import load_config as load_dispatch_config, dispatch as do_dispatch

        config = load_dispatch_config(config_path)
        dispatch_result = do_dispatch(result, contacts, config)

        print("\n# --- 分发结果 ---")
        print(json.dumps(dispatch_result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
