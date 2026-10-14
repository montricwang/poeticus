"""Poem Retrieval 的作品资格规则（融合前、融合后共用）。

仅剔除现有元数据足以明确排除的候选。朝代标签过于粗略，
无法确定同朝代作品或年代重叠作品的先后关系；
这些候选需要保留并标记不确定性，交由后续 Agent 判断。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Literal, Sequence

from backend.retrieval.poem.chronology import (
    ChronologyStatus,
    classify_dynasty_relation,
)
from backend.retrieval.poem.pipeline.fusion import FusedCandidate

RejectionReason = Literal["self_hit", "clearly_later"]


def classify_work_eligibility(
    work_id: str,
    dynasty: str | None,
    *,
    self_work_ids: Collection[str],
    target_dynasty: str | None,
) -> tuple[ChronologyStatus, RejectionReason | None]:
    """判断一个诗歌 Work 是否可作为候选，供两种排序顺序复用。"""
    chronology_status = classify_dynasty_relation(dynasty, target_dynasty)
    if work_id in self_work_ids:
        return chronology_status, "self_hit"
    if chronology_status == "clearly_later":
        return chronology_status, "clearly_later"
    return chronology_status, None


@dataclass(frozen=True)
class EligibleCandidate:
    """通过候选资格检查的作品及其年代关系。"""

    candidate: FusedCandidate
    chronology_status: ChronologyStatus


@dataclass(frozen=True)
class RejectedCandidate:
    """被排除的作品、排除原因及其年代关系。"""

    candidate: FusedCandidate
    reason: RejectionReason
    chronology_status: ChronologyStatus


@dataclass(frozen=True)
class EligibilityResult:
    """本次资格筛选保留和排除的两组候选。"""

    eligible: tuple[EligibleCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]


def apply_candidate_eligibility(
    candidates: Sequence[FusedCandidate],
    *,
    current_work_id: str | None,
    current_work_ids: Collection[str] | None = None,
    target_dynasty: str | None,
) -> EligibilityResult:
    """排除自身命中和明确晚出的作品，同时尽量保持召回率。

    同朝代、年代重叠或年代未知的候选继续保留，
    并传递 chronology_status，供后续 Agent 表达不确定性；
    不把粗粒度朝代信息误当成精确的作品先后证据。
    """
    eligible: list[EligibleCandidate] = []
    rejected: list[RejectedCandidate] = []
    self_work_ids = set(current_work_ids or ())
    if current_work_id:
        self_work_ids.add(current_work_id)

    for candidate in candidates:
        chronology_status, reason = classify_work_eligibility(
            candidate.work_id,
            candidate.dynasty,
            self_work_ids=self_work_ids,
            target_dynasty=target_dynasty,
        )
        if reason is not None:
            rejected.append(
                RejectedCandidate(
                    candidate=candidate,
                    reason=reason,
                    chronology_status=chronology_status,
                )
            )
            continue

        eligible.append(
            EligibleCandidate(
                candidate=candidate,
                chronology_status=chronology_status,
            )
        )

    return EligibilityResult(
        eligible=tuple(eligible),
        rejected=tuple(rejected),
    )
