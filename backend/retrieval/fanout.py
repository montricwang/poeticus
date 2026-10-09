"""将确定性的 Query Plan 分发给各个检索通道。

本模块只负责分发与汇集：

    Query Plan
        → 各 Dense / Lexical 通道
        → 每个 Query 与通道对应的排名结果

这里不负责融合分数或候选。后续 Fusion 不应直接比较
BM25 与余弦相似度的原始分数。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

from backend.retrieval.query_strategy import QueryVariant

RetrievalMethod = Literal["dense", "lexical"]
ChunkPolicy = Literal["sentence", "clause"]


@dataclass(frozen=True)
class RetrievalHit:
    """检索通道返回的一条已排名候选。"""

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
    """一条实际检索路径的稳定标识。"""

    name: str
    method: RetrievalMethod
    chunk_policy: ChunkPolicy


@dataclass(frozen=True)
class QueryChannelResult:
    """一个 QueryVariant 在一个通道上的排名结果。"""

    query: QueryVariant
    channel: ChannelDescriptor
    hits: tuple[RetrievalHit, ...]


class RetrievalChannel(Protocol):
    """支持批量查询的检索通道协议。

    一次调用接收全部去重后的查询文本，便于 Dense 通道批量编码
    并请求 ANN 索引，而不必为每条 Query 重新加载模型。
    """

    descriptor: ChannelDescriptor

    def search_many(
        self,
        queries: Sequence[str],
        *,
        top_k: int,
    ) -> Sequence[Sequence[RetrievalHit]]:
        """按输入 Query 的顺序，为每条 Query 返回一组已排名命中。"""
        ...


def execute_query_fanout(
    plan: Sequence[QueryVariant],
    channels: Sequence[RetrievalChannel],
    *,
    top_k: int,
) -> list[QueryChannelResult]:
    """将 Query Plan 中去重后的查询发往所有配置的通道。

    Query 的粒度与语料 Chunk 的粒度互相独立。因此，段落级 Query
    也可以进入 sentence 和 clause 通道，再由 Eval / Fusion 判断
    哪些通道提供了有价值的证据。
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
