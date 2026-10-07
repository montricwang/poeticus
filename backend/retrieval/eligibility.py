"""Candidate eligibility after multi-query retrieval and fusion.

This layer removes only candidates that current metadata can reject with high
confidence. Coarse dynasty labels are not precise enough to decide same-dynasty
or overlapping-period chronology, so those candidates are retained and marked
uncertain for later Agent adjudication.
"""
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
    """Filter self-hits and clearly later works without sacrificing recall.

    Same-dynasty, overlapping-period, and unknown chronology candidates remain
    eligible. Their chronology_status is preserved so downstream Agent logic
    can express uncertainty rather than pretending coarse dynasty metadata
    proves exact precedence.
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
