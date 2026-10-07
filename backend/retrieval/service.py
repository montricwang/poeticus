"""Product-facing orchestration for Text Retrieval.

This module composes the backend-independent retrieval stages:

    text
    -> deterministic Query Plan
    -> configured Retrieval channels
    -> Work-level RRF
    -> conservative Candidate Eligibility
    -> final Tool-ready candidate list

Storage / ANN choices stay behind RetrievalChannel implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Literal, Sequence

from backend.retrieval.eligibility import (
    EligibleCandidate,
    RejectedCandidate,
    apply_candidate_eligibility,
)
from backend.retrieval.fanout import RetrievalChannel, execute_query_fanout
from backend.retrieval.fusion import DEFAULT_RRF_K, fuse_candidates_rrf
from backend.retrieval.query_strategy import QueryVariant, build_query_plan

RetrievalStatus = Literal["ok", "no_hit"]


@dataclass(frozen=True)
class TextRetrievalResult:
    status: RetrievalStatus
    candidates: tuple[EligibleCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]
    query_plan: tuple[QueryVariant, ...]
    channel_count: int
    per_channel_top_k: int


class TextRetrievalService:
    """Compose query planning, fan-out, fusion, and eligibility.

    The service does not know whether a channel is backed by FAISS, pgvector,
    SQLite FTS5, or another store. It only depends on the RetrievalChannel
    contract.
    """

    def __init__(
        self,
        channels: Sequence[RetrievalChannel],
        *,
        per_channel_top_k: int = 20,
        final_top_k: int = 5,
        rrf_k: int = DEFAULT_RRF_K,
    ):
        if not channels:
            raise ValueError("Text Retrieval 至少需要一个 channel")
        if per_channel_top_k <= 0:
            raise ValueError("per_channel_top_k 必须为正整数")
        if final_top_k <= 0:
            raise ValueError("final_top_k 必须为正整数")
        if rrf_k < 0:
            raise ValueError("rrf_k 不能为负数")

        names = [channel.descriptor.name for channel in channels]
        if len(names) != len(set(names)):
            raise ValueError("Retrieval channel name 不能重复")

        self._channels = tuple(channels)
        self._per_channel_top_k = per_channel_top_k
        self._final_top_k = final_top_k
        self._rrf_k = rrf_k

    def search(
        self,
        text: str,
        *,
        current_work_id: str | None,
        current_work_ids: Collection[str] | None = None,
        target_dynasty: str | None,
    ) -> TextRetrievalResult:
        plan = tuple(build_query_plan(text))
        channel_results = execute_query_fanout(
            plan,
            self._channels,
            top_k=self._per_channel_top_k,
        )

        # Fuse the complete bounded candidate pool first. If we truncated the
        # fused list before eligibility, self-hits / clearly-later works could
        # consume final slots and hide valid candidates below them.
        fused = fuse_candidates_rrf(
            channel_results,
            top_k=None,
            rrf_k=self._rrf_k,
        )
        eligibility = apply_candidate_eligibility(
            fused,
            current_work_id=current_work_id,
            current_work_ids=current_work_ids,
            target_dynasty=target_dynasty,
        )

        candidates = eligibility.eligible[: self._final_top_k]
        return TextRetrievalResult(
            status="ok" if candidates else "no_hit",
            candidates=candidates,
            rejected=eligibility.rejected,
            query_plan=plan,
            channel_count=len(self._channels),
            per_channel_top_k=self._per_channel_top_k,
        )
