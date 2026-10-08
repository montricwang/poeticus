"""Execute a deterministic Query Plan across retrieval channels.

This module owns orchestration only:

    Query Plan
    -> each configured Dense / Lexical channel
    -> per-query, per-channel ranked results

It deliberately does not fuse scores or candidates. Candidate Fusion is the
next layer and should not depend on BM25 / cosine score scales.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

from backend.retrieval.query_strategy import QueryVariant

RetrievalMethod = Literal["dense", "lexical"]
ChunkPolicy = Literal["sentence", "clause"]


@dataclass(frozen=True)
class RetrievalHit:
    """One ranked candidate returned by a retrieval channel."""

    rank: int
    chunk_id: str
    work_id: str
    text: str
    title: str | None = None
    author: str | None = None
    dynasty: str | None = None
    source_record_id: str | None = None
    score: float | None = None
    score_name: str | None = None


@dataclass(frozen=True)
class ChannelDescriptor:
    """Stable identity of one physical retrieval path."""

    name: str
    method: RetrievalMethod
    chunk_policy: ChunkPolicy


@dataclass(frozen=True)
class QueryChannelResult:
    """Ranked output for one QueryVariant against one channel."""

    query: QueryVariant
    channel: ChannelDescriptor
    hits: tuple[RetrievalHit, ...]


class RetrievalChannel(Protocol):
    """Batch-oriented retrieval channel.

    A channel receives all unique query texts in one call. This lets a future
    Dense implementation batch query encoding / ANN requests instead of
    reloading a model once per query.
    """

    descriptor: ChannelDescriptor

    def search_many(
        self,
        queries: Sequence[str],
        *,
        top_k: int,
    ) -> Sequence[Sequence[RetrievalHit]]:
        """Return one ranked hit list for every input query, in the same order."""
        ...


def execute_query_fanout(
    plan: Sequence[QueryVariant],
    channels: Sequence[RetrievalChannel],
    *,
    top_k: int,
) -> list[QueryChannelResult]:
    """Run every unique planned query through every configured channel.

    Query granularity and corpus chunk granularity are intentionally
    independent. A passage query may therefore be searched against both
    sentence and clause channels; later Eval / Fusion can decide which paths
    contribute useful evidence.
    """
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    if not plan or not channels:
        return []

    queries = [variant.text for variant in plan]
    outputs: list[tuple[ChannelDescriptor, tuple[tuple[RetrievalHit, ...], ...]]] = []

    for channel in channels:
        raw = channel.search_many(queries, top_k=top_k)
        if len(raw) != len(plan):
            raise ValueError(
                f"Retrieval channel {channel.descriptor.name!r} 返回 {len(raw)} "
                f"组结果，预期 {len(plan)} 组"
            )

        normalized: list[tuple[RetrievalHit, ...]] = []
        for query_index, hits in enumerate(raw):
            ranked = tuple(hits)
            for expected_rank, hit in enumerate(ranked, 1):
                if hit.rank != expected_rank:
                    raise ValueError(
                        f"Retrieval channel {channel.descriptor.name!r} "
                        f"query[{query_index}] rank 不连续："
                        f"expected={expected_rank}, actual={hit.rank}"
                    )
            normalized.append(ranked)

        outputs.append((channel.descriptor, tuple(normalized)))

    results: list[QueryChannelResult] = []
    for query_index, variant in enumerate(plan):
        for descriptor, channel_output in outputs:
            results.append(
                QueryChannelResult(
                    query=variant,
                    channel=descriptor,
                    hits=channel_output[query_index],
                )
            )
    return results
