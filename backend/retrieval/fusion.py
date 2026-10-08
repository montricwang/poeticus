"""Work-level Reciprocal Rank Fusion for Text Retrieval.

Each QueryVariant × RetrievalChannel result is one ranked list. The fusion
layer collapses repeated chunks from the same Work inside a single list, then
adds one RRF contribution per list:

    contribution = 1 / (rrf_k + rank)

This lets Dense / Lexical and sentence / clause paths vote together without
normalizing cosine and BM25 score scales.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypedDict

from backend.retrieval.fanout import (
    ChannelDescriptor,
    QueryChannelResult,
    RetrievalHit,
)
from backend.retrieval.query_strategy import QueryOrigin

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusionEvidence:
    """One list-level vote supporting a fused Work candidate."""

    query_text: str
    query_origins: tuple[QueryOrigin, ...]
    channel: ChannelDescriptor
    hit: RetrievalHit
    contribution: float


@dataclass(frozen=True)
class FusedCandidate:
    """One Work-level candidate after multi-query / multi-channel fusion."""

    work_id: str
    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None
    rrf_score: float
    best_rank: int
    support_count: int
    evidences: tuple[FusionEvidence, ...]


class _FusionAccumulator(TypedDict):
    """Mutable, typed work-level RRF state used only during fusion."""

    title: str | None
    author: str | None
    dynasty: str | None
    source_record_id: str | None
    rrf_score: float
    best_rank: int
    evidences: list[FusionEvidence]


def _assert_metadata_consistent(
    *,
    work_id: str,
    field: str,
    current: str | None,
    incoming: str | None,
) -> str | None:
    if current is None:
        return incoming
    if incoming is None or incoming == current:
        return current
    raise ValueError(
        f"同一 work_id={work_id!r} 的 {field} 不一致："
        f"{current!r} != {incoming!r}"
    )


def fuse_candidates_rrf(
    results: Sequence[QueryChannelResult],
    *,
    top_k: int | None,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[FusedCandidate]:
    """Fuse ranked chunk results into Work-level candidates with RRF.

    A Work contributes at most once per ranked list. If several chunks from
    the same Work appear in one list, only the best-ranked chunk contributes
    to RRF. This prevents long works from gaining extra score merely because
    they produced more chunks.

    All contributing list-level evidences are retained for later explanation
    or LLM adjudication.
    """
    if top_k is not None and top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    if rrf_k < 0:
        raise ValueError("rrf_k 不能为负数")

    accumulators: dict[str, _FusionAccumulator] = {}

    for result in results:
        seen_in_list: set[str] = set()

        for hit in result.hits:
            if hit.work_id in seen_in_list:
                continue
            seen_in_list.add(hit.work_id)

            contribution = 1.0 / (rrf_k + hit.rank)
            accumulator = accumulators.get(hit.work_id)

            if accumulator is None:
                accumulator = _FusionAccumulator(
                    title=hit.title,
                    author=hit.author,
                    dynasty=hit.dynasty,
                    source_record_id=hit.source_record_id,
                    rrf_score=0.0,
                    best_rank=hit.rank,
                    evidences=[],
                )
                accumulators[hit.work_id] = accumulator
            else:
                for field in ("title", "author", "dynasty", "source_record_id"):
                    accumulator[field] = _assert_metadata_consistent(
                        work_id=hit.work_id,
                        field=field,
                        current=accumulator[field],
                        incoming=getattr(hit, field),
                    )
                accumulator["best_rank"] = min(
                    accumulator["best_rank"],
                    hit.rank,
                )

            accumulator["rrf_score"] += contribution
            accumulator["evidences"].append(
                FusionEvidence(
                    query_text=result.query.text,
                    query_origins=result.query.origins,
                    channel=result.channel,
                    hit=hit,
                    contribution=contribution,
                )
            )

    candidates = [
        FusedCandidate(
            work_id=work_id,
            title=accumulator["title"],
            author=accumulator["author"],
            dynasty=accumulator["dynasty"],
            source_record_id=accumulator["source_record_id"],
            rrf_score=accumulator["rrf_score"],
            best_rank=accumulator["best_rank"],
            support_count=len(accumulator["evidences"]),
            evidences=tuple(accumulator["evidences"]),
        )
        for work_id, accumulator in accumulators.items()
    ]

    candidates.sort(
        key=lambda candidate: (
            -candidate.rrf_score,
            candidate.best_rank,
            candidate.work_id,
        )
    )
    return candidates if top_k is None else candidates[:top_k]
