"""多路检索和融合后的候选资格筛选。

仅剔除现有元数据足以明确排除的候选。朝代标签过于粗略，
无法确定同朝代作品或年代重叠作品的先后关系；
这些候选需要保留并标记不确定性，交由后续 Agent 判断。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Literal, Sequence

from backend.retrieval.chronology import (
    ChronologyStatus,
    classify_dynasty_relation,
)
from backend.retrieval.fusion import FusedCandidate

RejectionReason = Literal["self_hit", "clearly_later"]


@dataclass(frozen=True)
class EligibleCandidate:
    candidate: FusedCandidate
    chronology_status: ChronologyStatus


@dataclass(frozen=True)
class RejectedCandidate:
    candidate: FusedCandidate
    reason: RejectionReason
    chronology_status: ChronologyStatus


@dataclass(frozen=True)
class EligibilityResult:
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
        chronology_status = classify_dynasty_relation(
            candidate.dynasty,
            target_dynasty,
        )

        if candidate.work_id in self_work_ids:
            rejected.append(
                RejectedCandidate(
                    candidate=candidate,
                    reason="self_hit",
                    chronology_status=chronology_status,
                )
            )
            continue

        if chronology_status == "clearly_later":
            rejected.append(
                RejectedCandidate(
                    candidate=candidate,
                    reason="clearly_later",
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
