import math

import pytest

from backend.retrieval.fanout import (
    ChannelDescriptor,
    QueryChannelResult,
    RetrievalHit,
)
from backend.retrieval.fusion import fuse_candidates_rrf
from backend.retrieval.query_strategy import build_query_plan


def _result(query, channel_name, method, chunk_policy, hits):
    return QueryChannelResult(
        query=query,
        channel=ChannelDescriptor(
            name=channel_name,
            method=method,
            chunk_policy=chunk_policy,
        ),
        hits=tuple(hits),
    )


def _hit(rank, *, work_id, chunk_id=None, text=None, **metadata):
    return RetrievalHit(
        rank=rank,
        chunk_id=chunk_id or f"{work_id}:{rank}",
        work_id=work_id,
        text=text or f"{work_id} 候选",
        **metadata,
    )


def test_rrf_combines_support_across_dense_and_lexical_lists():
    query = build_query_plan("甲。")[0]
    results = [
        _result(
            query,
            "dense_sentence",
            "dense",
            "sentence",
            [_hit(1, work_id="a"), _hit(2, work_id="b")],
        ),
        _result(
            query,
            "lexical_sentence",
            "lexical",
            "sentence",
            [_hit(1, work_id="b"), _hit(3, work_id="a")],
        ),
    ]

    fused = fuse_candidates_rrf(results, top_k=10)

    assert [candidate.work_id for candidate in fused] == ["b", "a"]
    assert fused[0].support_count == 2
    assert fused[1].support_count == 2
    assert math.isclose(
        fused[0].rrf_score,
        1 / 62 + 1 / 61,
    )
    assert math.isclose(
        fused[1].rrf_score,
        1 / 61 + 1 / 63,
    )


def test_rrf_merges_sentence_and_clause_hits_at_work_level():
    query = build_query_plan("片片轻鸥落晚沙。")[0]
    results = [
        _result(
            query,
            "dense_sentence",
            "dense",
            "sentence",
            [
                _hit(
                    5,
                    work_id="dufu",
                    chunk_id="dufu:sentence:3",
                    text="娟娟戏蝶过闲幔，片片轻鸥下急湍。",
                )
            ],
        ),
        _result(
            query,
            "dense_clause",
            "dense",
            "clause",
            [
                _hit(
                    2,
                    work_id="dufu",
                    chunk_id="dufu:clause:7",
                    text="片片轻鸥下急湍。",
                )
            ],
        ),
    ]

    fused = fuse_candidates_rrf(results, top_k=10)

    assert len(fused) == 1
    assert fused[0].work_id == "dufu"
    assert fused[0].support_count == 2
    assert {evidence.hit.chunk_id for evidence in fused[0].evidences} == {
        "dufu:sentence:3",
        "dufu:clause:7",
    }


def test_same_work_contributes_only_once_inside_one_ranked_list():
    query = build_query_plan("甲。")[0]
    result = _result(
        query,
        "dense_sentence",
        "dense",
        "sentence",
        [
            _hit(1, work_id="long-work", chunk_id="long:1"),
            _hit(2, work_id="long-work", chunk_id="long:2"),
            _hit(3, work_id="other"),
        ],
    )

    fused = fuse_candidates_rrf([result], top_k=10)

    long_work = next(candidate for candidate in fused if candidate.work_id == "long-work")
    assert long_work.support_count == 1
    assert math.isclose(long_work.rrf_score, 1 / 61)
    assert [evidence.hit.chunk_id for evidence in long_work.evidences] == ["long:1"]


def test_rrf_preserves_query_and_channel_provenance():
    plan = build_query_plan("甲，乙。")
    passage = plan[0]
    clause = next(variant for variant in plan if variant.text == "甲，")
    results = [
        _result(
            passage,
            "lexical_sentence",
            "lexical",
            "sentence",
            [_hit(2, work_id="w")],
        ),
        _result(
            clause,
            "dense_clause",
            "dense",
            "clause",
            [_hit(1, work_id="w")],
        ),
    ]

    fused = fuse_candidates_rrf(results, top_k=5)

    assert fused[0].support_count == 2
    assert {
        (evidence.query_text, evidence.channel.name)
        for evidence in fused[0].evidences
    } == {
        ("甲，乙。", "lexical_sentence"),
        ("甲，", "dense_clause"),
    }


def test_rrf_rejects_conflicting_work_metadata():
    query = build_query_plan("甲。")[0]
    results = [
        _result(
            query,
            "dense",
            "dense",
            "sentence",
            [_hit(1, work_id="w", author="作者甲")],
        ),
        _result(
            query,
            "lexical",
            "lexical",
            "sentence",
            [_hit(1, work_id="w", author="作者乙")],
        ),
    ]

    with pytest.raises(ValueError, match="author 不一致"):
        fuse_candidates_rrf(results, top_k=10)


def test_rrf_uses_best_rank_then_work_id_as_stable_tiebreakers():
    query = build_query_plan("甲。")[0]
    # QueryChannelResult 通常接收 Fan-out 生成的有效排名。
    # 本测试直接构造相同的 RRF 分数，以验证最终排序的稳定性。
    fused = fuse_candidates_rrf(
        [
            _result(query, "one", "dense", "sentence", [_hit(1, work_id="b")]),
            _result(query, "two", "lexical", "sentence", [_hit(1, work_id="a")]),
        ],
        top_k=10,
    )

    assert [candidate.work_id for candidate in fused] == ["a", "b"]


def test_rrf_validates_parameters_and_respects_top_k():
    query = build_query_plan("甲。")[0]
    results = [
        _result(
            query,
            "dense",
            "dense",
            "sentence",
            [
                _hit(1, work_id="a"),
                _hit(2, work_id="b"),
            ],
        )
    ]

    assert len(fuse_candidates_rrf(results, top_k=1)) == 1

    with pytest.raises(ValueError, match="top_k"):
        fuse_candidates_rrf(results, top_k=0)

    with pytest.raises(ValueError, match="rrf_k"):
        fuse_candidates_rrf(results, top_k=10, rrf_k=-1)


def test_rrf_can_return_complete_fused_pool():
    query = build_query_plan("甲。")[0]
    results = [
        _result(
            query,
            "dense",
            "dense",
            "sentence",
            [
                _hit(1, work_id="a"),
                _hit(2, work_id="b"),
                _hit(3, work_id="c"),
            ],
        )
    ]

    fused = fuse_candidates_rrf(results, top_k=None)

    assert [candidate.work_id for candidate in fused] == ["a", "b", "c"]
