"""面向产品的 Text Retrieval 检索流程编排。

本模块依次调用与底层存储无关的检索阶段：

    文本 → Query Plan → 检索通道 → Work-level RRF
         → Candidate Eligibility → 提供给 Agent 的最终候选

FAISS、ANN 或 SQLite 的实现细节留在 RetrievalChannel 内部。"""
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
    """组合 Query Plan、Fan-out、Fusion 和 Eligibility。

    本服务不关心通道底层使用 FAISS、pgvector、SQLite FTS5
    还是其他存储，只依赖 RetrievalChannel 接口契约。
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
        target_dynasty: str | None,
        current_work_ids: Collection[str] | None = None,
    ) -> TextRetrievalResult:
        plan = tuple(build_query_plan(text))
        channel_results = execute_query_fanout(
            plan,
            self._channels,
            top_k=self._per_channel_top_k,
        )

        # 先融合全部有上限的候选池，再执行 Eligibility。
        # 如果先截断融合结果，自身命中或明确晚出的作品会占用最终名额，
        # 排名稍后的有效候选就可能被错误丢弃。
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
