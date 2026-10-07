from backend.retrieval.fanout import (
    ChannelDescriptor,
    RetrievalHit,
    execute_query_fanout,
)
from backend.retrieval.query_strategy import build_query_plan


class FakeChannel:
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.calls = []

    def search_many(self, queries, *, top_k):
        self.calls.append((list(queries), top_k))
        return [
            [
                RetrievalHit(
                    rank=1,
                    chunk_id=f"{self.descriptor.name}:{index}",
                    work_id=f"work:{index}",
                    text=f"候选 {query}",
                    score=1.0,
                    score_name="fake",
                )
            ]
            for index, query in enumerate(queries)
        ]


def test_execute_query_fanout_calls_each_channel_once_with_all_unique_queries():
    plan = build_query_plan("甲，乙。")
    dense = FakeChannel(
        ChannelDescriptor(
            name="dense_sentence",
            method="dense",
            chunk_policy="sentence",
        )
    )
    lexical = FakeChannel(
        ChannelDescriptor(
            name="lexical_sentence",
            method="lexical",
            chunk_policy="sentence",
        )
    )

    results = execute_query_fanout(plan, [dense, lexical], top_k=20)

    expected_queries = [variant.text for variant in plan]
    assert dense.calls == [(expected_queries, 20)]
    assert lexical.calls == [(expected_queries, 20)]
    assert len(results) == len(plan) * 2


def test_execute_query_fanout_keeps_query_provenance_and_channel_identity():
    plan = build_query_plan("片片轻鸥落晚沙。")
    channel = FakeChannel(
        ChannelDescriptor(
            name="dense_clause",
            method="dense",
            chunk_policy="clause",
        )
    )

    results = execute_query_fanout(plan, [channel], top_k=5)

    assert len(results) == 1
    result = results[0]
    assert result.channel.name == "dense_clause"
    assert result.channel.method == "dense"
    assert result.channel.chunk_policy == "clause"
    assert [origin.level for origin in result.query.origins] == [
        "passage",
        "sentence",
        "clause",
    ]
    assert result.hits[0].chunk_id == "dense_clause:0"


def test_query_granularity_and_corpus_chunk_policy_are_independent():
    plan = build_query_plan("甲，乙。")
    dense_sentence = FakeChannel(
        ChannelDescriptor("dense_sentence", "dense", "sentence")
    )
    dense_clause = FakeChannel(
        ChannelDescriptor("dense_clause", "dense", "clause")
    )

    results = execute_query_fanout(
        plan,
        [dense_sentence, dense_clause],
        top_k=3,
    )

    passage_results = [
        result
        for result in results
        if result.query.origins[0].level == "passage"
    ]
    assert {result.channel.chunk_policy for result in passage_results} == {
        "sentence",
        "clause",
    }


def test_execute_query_fanout_rejects_channel_result_count_mismatch():
    plan = build_query_plan("甲，乙。")

    class BrokenChannel:
        descriptor = ChannelDescriptor("broken", "lexical", "sentence")

        def search_many(self, queries, *, top_k):
            return []

    try:
        execute_query_fanout(plan, [BrokenChannel()], top_k=10)
    except ValueError as exc:
        assert "预期" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_execute_query_fanout_rejects_non_contiguous_ranks():
    plan = build_query_plan("甲。")

    class BrokenRankChannel:
        descriptor = ChannelDescriptor("broken_rank", "dense", "sentence")

        def search_many(self, queries, *, top_k):
            return [
                [
                    RetrievalHit(
                        rank=2,
                        chunk_id="c",
                        work_id="w",
                        text="候选",
                    )
                ]
            ]

    try:
        execute_query_fanout(plan, [BrokenRankChannel()], top_k=10)
    except ValueError as exc:
        assert "rank 不连续" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_execute_query_fanout_handles_empty_plan_or_channels():
    plan = build_query_plan("甲。")
    channel = FakeChannel(ChannelDescriptor("dense", "dense", "sentence"))

    assert execute_query_fanout([], [channel], top_k=5) == []
    assert execute_query_fanout(plan, [], top_k=5) == []
    assert channel.calls == []
