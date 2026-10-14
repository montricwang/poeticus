"""使用 Werneror 诗词语料的朝代标签作保守的先后分类。

不保存年份，也不把粗略标签当作作者或作品的精确编年。
"""
from __future__ import annotations

from typing import Literal

ChronologyStatus = Literal[
    "clearly_earlier",
    "clearly_later",
    "same_dynasty",
    "overlapping",
    "unknown",
]

# 本诗歌库的 27 个标签：大致按时期开始顺序排列。
# 并列元组表示两个标签没有可区分的起点。
_DYNASTY_START_ORDER = (
    ("先秦",),
    ("秦",),
    ("汉",),
    ("魏晋",),
    ("魏晋末南北朝初",),
    ("南北朝",),
    ("隋",),
    ("隋末唐初",),
    ("唐",),
    ("唐末宋初",),
    ("辽",),
    ("宋",),
    ("宋末金初",),
    ("金",),
    ("金末元初",),
    ("宋末元初",),
    ("元",),
    ("元末明初",),
    ("明",),
    ("明末清初",),
    ("清",),
    ("清末民国初", "清末近现代初"),
    ("近现代",),
    ("民国末当代初", "近现代末当代初"),
    ("当代",),
)

_START_POSITION = {
    label: index
    for index, group in enumerate(_DYNASTY_START_ORDER)
    for label in group
}
KNOWN_DYNASTIES = frozenset(_START_POSITION)

# 同组内的任意两个标签都交叠或并立，不能直接断定作品先后。
# 交叠不具传递性：辽与宋、宋与元交叠，不意味着辽与元交叠。
_OVERLAP_GROUPS = (
    frozenset(("先秦", "秦")),
    frozenset(("秦", "汉")),
    frozenset(("汉", "魏晋")),
    frozenset(("魏晋", "魏晋末南北朝初", "南北朝")),
    frozenset(("南北朝", "隋")),
    frozenset(("隋", "隋末唐初", "唐")),
    frozenset(("唐", "唐末宋初")),
    frozenset(("唐末宋初", "辽", "宋")),
    frozenset(("辽", "宋", "宋末金初", "金")),
    frozenset(("宋", "金", "金末元初")),
    frozenset(("宋", "宋末元初", "金末元初", "元")),
    frozenset(("元", "元末明初", "明")),
    frozenset(("明", "明末清初", "清")),
    frozenset(("清", "清末民国初", "清末近现代初", "近现代")),
    frozenset(("近现代", "民国末当代初", "近现代末当代初", "当代")),
)


def classify_dynasty_relation(
    candidate_dynasty: str | None,
    target_dynasty: str | None,
) -> ChronologyStatus:
    """只根据本库标签判断能否确定先后，不推断作品实际创作年代。"""
    if (
        candidate_dynasty not in KNOWN_DYNASTIES
        or target_dynasty not in KNOWN_DYNASTIES
    ):
        return "unknown"
    if candidate_dynasty == target_dynasty:
        return "same_dynasty"
    if any(
        candidate_dynasty in group and target_dynasty in group
        for group in _OVERLAP_GROUPS
    ):
        return "overlapping"
    if _START_POSITION[candidate_dynasty] < _START_POSITION[target_dynasty]:
        return "clearly_earlier"
    return "clearly_later"


def candidate_prior_dynasties(target_dynasty: str) -> set[str]:
    """兼容旧诊断脚本的严格前代筛选（与在线宽松筛选不同）。"""
    if target_dynasty not in KNOWN_DYNASTIES:
        raise ValueError(
            f"尚未定义朝代标签：{target_dynasty!r}；"
            "不能安全地做前代过滤"
        )

    allowed: set[str] = set()
    for candidate in KNOWN_DYNASTIES:
        relation = classify_dynasty_relation(candidate, target_dynasty)
        if relation == "clearly_earlier":
            allowed.add(candidate)
        elif (
            relation == "overlapping"
            and "末" in candidate
            and "初" in candidate
            and _START_POSITION[candidate] < _START_POSITION[target_dynasty]
        ):
            allowed.add(candidate)
    return allowed
