"""Shared coarse chronology helpers for Text Retrieval.

Dynasty metadata is deliberately treated as a coarse interval, not as a
substitute for author/work dates. Product candidate filtering should only
remove candidates that are clearly later than the current work's dynasty;
same-dynasty and overlapping periods remain uncertain.
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

# Coarse chronology for the current Werneror labels.
DYNASTY_PERIODS = {
    "先秦": (-3000, -221),
    "秦": (-221, -206),
    "汉": (-206, 220),
    "魏晋": (220, 420),
    "魏晋末南北朝初": (400, 440),
    "南北朝": (420, 589),
    "隋": (581, 618),
    "隋末唐初": (610, 630),
    "唐": (618, 907),
    "唐末宋初": (880, 1000),
    "辽": (916, 1125),
    "宋": (960, 1279),
    "金": (1115, 1234),
    "宋末金初": (1110, 1140),
    "宋末元初": (1250, 1300),
    "金末元初": (1210, 1300),
    "元": (1271, 1368),
    "元末明初": (1350, 1400),
    "明": (1368, 1644),
    "明末清初": (1620, 1680),
    "清": (1636, 1912),
    "清末民国初": (1890, 1930),
    "清末近现代初": (1890, 1930),
    "近现代": (1912, 1949),
    "民国末当代初": (1940, 1960),
    "近现代末当代初": (1940, 1960),
    "当代": (1949, 2100),
}


def classify_dynasty_relation(
    candidate_dynasty: str | None,
    target_dynasty: str | None,
) -> ChronologyStatus:
    """Classify only what dynasty-level intervals can safely tell us."""
    if (
        not candidate_dynasty
        or not target_dynasty
        or candidate_dynasty not in DYNASTY_PERIODS
        or target_dynasty not in DYNASTY_PERIODS
    ):
        return "unknown"

    if candidate_dynasty == target_dynasty:
        return "same_dynasty"

    candidate_start, candidate_end = DYNASTY_PERIODS[candidate_dynasty]
    target_start, target_end = DYNASTY_PERIODS[target_dynasty]

    if candidate_end < target_start:
        return "clearly_earlier"
    if candidate_start > target_end:
        return "clearly_later"
    return "overlapping"


def candidate_prior_dynasties(target_dynasty: str) -> set[str]:
    """Legacy strict coarse filter used by current diagnostic search scripts.

    This preserves the existing Exact/BM25 diagnostic semantics: fully earlier
    periods plus transition labels that begin before the target dynasty and
    overlap its start. Product candidate eligibility is intentionally more
    conservative and uses classify_dynasty_relation() instead.
    """
    if target_dynasty not in DYNASTY_PERIODS:
        raise ValueError(
            f"尚未定义朝代时间范围：{target_dynasty!r}；"
            "不能安全地做前代过滤"
        )

    target_start, _ = DYNASTY_PERIODS[target_dynasty]
    allowed = set()
    for dynasty, (candidate_start, candidate_end) in DYNASTY_PERIODS.items():
        if dynasty == target_dynasty:
            continue

        fully_earlier = candidate_end < target_start
        transitional_overlap = (
            candidate_start < target_start <= candidate_end
            and "末" in dynasty
            and "初" in dynasty
        )
        if fully_earlier or transitional_overlap:
            allowed.add(dynasty)

    return allowed
