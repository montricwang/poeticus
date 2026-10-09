"""将 Text Retrieval 的多路结果按 Work 进行 RRF 融合。

每个 QueryVariant × RetrievalChannel 对应一条排名列表。
同一列表中属于同一 Work 的多个 Chunk 先去重，
每个 Work 在该列表中只贡献一次 RRF 分数：

    contribution = 1 / (rrf_k + rank)

这样 Dense、Lexical、sentence、clause 等路径可以共同投票，
不需要强行统一余弦相似度与 BM25 的分数尺度。"""
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
    """一条排名列表为融合后 Work 候选提供的一次支持。"""

    query_text: str
    query_origins: tuple[QueryOrigin, ...]
    channel: ChannelDescriptor
    hit: RetrievalHit
    contribution: float


@dataclass(frozen=True)
class FusedCandidate:
    """多 Query、多通道融合后的一个 Work 级候选。"""

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
    """仅在融合计算期间使用的可变 Work 级 RRF 状态。"""

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
    """使用 RRF 将各 Chunk 排名结果融合为 Work 级候选。

    同一 Work 在每条排名列表中最多贡献一次分数。如果它的多个
    Chunk 同时命中，只采用排名最高的 Chunk，避免长篇作品因为
    切分出更多 Chunk 而获得不合理的额外分数。

    保留所有参与融合的列表级证据，供后续解释或 LLM 判断。
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
