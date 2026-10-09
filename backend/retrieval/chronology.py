"""Text Retrieval 共用的粗粒度年代判断。

朝代元数据只提供大致时间区间，不能代替作者或作品的确切年代。
产品筛选仅剔除明确晚于当前作品所属朝代的候选；
同朝代及年代重叠的候选保留为待判断项。"""
from __future__ import annotations

from typing import Literal

ChronologyStatus = Literal[
    "clearly_earlier",
    "clearly_later",
    "same_dynasty",
    "overlapping",
    "unknown",
]

# 根据当前 Werneror 语料的朝代标签建立粗粒度年代区间。
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
    """只判断朝代区间足以明确支持的年代关系。"""
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
    """保留给诊断脚本使用的旧版严格前代筛选。

    包含完全早于目标朝代的时期，也包含起始于目标朝代之前、
    与其早期重叠的过渡朝代标签，以维持 Exact/BM25 的诊断语义。
    产品候选筛选更谨慎，改用 classify_dynasty_relation()。
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
