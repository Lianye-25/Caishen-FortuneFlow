"""
财神 联系人模糊匹配引擎

纯标准库实现，零外部依赖。支持 ASR 容错（同音字、近似发音）和职称后缀剥离。
"""

import difflib
import json
import os
from typing import Optional


# 常见中文职称后缀，匹配时会尝试剥离以提高命中率
TITLE_SUFFIXES = ["总", "经理", "总监", "工", "老师", "主管", "主任", "董", "老板"]


def load_contacts(contacts_path: str) -> dict:
    """加载 contacts.json 文件，返回完整字典。"""
    if not os.path.exists(contacts_path):
        return {"superiors": [], "subordinates": [], "agents": []}
    with open(contacts_path, "r", encoding="utf-8") as f:
        return json.load(f)


def match_contact(name: str, contact_list: list[dict], threshold: float = 0.7) -> Optional[dict]:
    """
    在联系人列表中模糊匹配名称。

    匹配策略：
    1. 精确匹配（原始名称）→ match_type="exact"
    2. 剥离职称后缀后精确匹配 → match_type="exact"
    3. 模糊匹配（SequenceMatcher ≥ threshold）→ match_type="fuzzy"
    4. 剥离后缀后模糊匹配 → match_type="fuzzy"
    5. 无匹配 → None

    Args:
        name: 待匹配的名称（来自语音 ASR）
        contact_list: 联系人列表
        threshold: 模糊匹配阈值，默认 0.7

    Returns:
        匹配到的联系人 dict（含 match_type 字段），或 None
    """
    if not name or not contact_list:
        return None

    name_clean = name.strip()
    name_no_title = _strip_title(name_clean)

    best_match = None
    best_ratio = 0.0
    best_match_type = "none"

    for contact in contact_list:
        contact_name = contact.get("name", "")

        # 1. 精确匹配
        if name_clean == contact_name:
            result = dict(contact)
            result["match_type"] = "exact"
            return result

        # 2. 剥离后缀后精确匹配
        if name_no_title and name_no_title == _strip_title(contact_name):
            result = dict(contact)
            result["match_type"] = "exact"
            return result

        # 3. 模糊匹配（原始名称）
        ratio = difflib.SequenceMatcher(None, name_clean, contact_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = contact
            best_match_type = "fuzzy" if ratio >= threshold else "none"

        # 4. 剥离后缀后模糊匹配
        if name_no_title:
            ratio_no_title = difflib.SequenceMatcher(
                None, name_no_title, _strip_title(contact_name)
            ).ratio()
            if ratio_no_title > best_ratio:
                best_ratio = ratio_no_title
                best_match = contact
                best_match_type = "fuzzy" if ratio_no_title >= threshold else "none"

    if best_match and best_match_type != "none":
        result = dict(best_match)
        result["match_type"] = best_match_type
        return result

    return None


def match_in_list(name: str, contact_list: list[dict], threshold: float = 0.7) -> dict:
    """
    在列表中匹配，返回标准结果字典（含 candidates 列表）。
    始终返回有效字典，无匹配时 match_type 为 "none"。
    """
    # 收集所有候选项（模糊匹配得分 ≥ 0.4）
    candidates = []
    for contact in contact_list:
        contact_name = contact.get("name", "")
        ratio = difflib.SequenceMatcher(None, name.strip(), contact_name).ratio()
        name_no_title = _strip_title(name.strip())
        if name_no_title:
            ratio2 = difflib.SequenceMatcher(
                None, name_no_title, _strip_title(contact_name)
            ).ratio()
            ratio = max(ratio, ratio2)
        if ratio >= 0.4:
            candidates.append({"name": contact_name, "score": round(ratio, 2)})

    candidates.sort(key=lambda x: x["score"], reverse=True)

    best = match_contact(name, contact_list, threshold)
    if best:
        best["candidates"] = [c["name"] for c in candidates[:3]]
        return best

    return {
        "name": name,
        "match_type": "none",
        "candidates": [c["name"] for c in candidates[:3]],
    }


def _strip_title(name: str) -> str:
    """剥离名称末尾的职称后缀。"""
    for suffix in sorted(TITLE_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name
