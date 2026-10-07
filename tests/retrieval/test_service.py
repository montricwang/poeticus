from backend.retrieval.fanout import (
    ChannelDescriptor,
    RetrievalHit,
)
from backend.retrieval.service import TextRetrievalService


class FakeChannel:
    def __init__(self, name, method, chunk_policy, rows_by_query):
        self.descriptor = ChannelDescriptor(name, method, chunk_policy)
        self.rows_by_query = rows_by_query
        self.calls = []

    def search_many(self, queries, *, top_k):
        self.calls.append((list(queries), top_k))
        output = []
        for query in queries:
            rows = self.rows_by_query.get(query, [])
            output.append(
                [
                    RetrievalHit(
                        rank=index,
                        chunk_id=row["chunk_id"],
                        work_id=row["work_id"],
                        text=row["text"],
                        title=row.get("title"),
                        author=row.get("author"),
                        dynasty=row.get("dynasty"),
                        source_record_id=row.get("source_record_id"),
                        score=row.get("score"),
                        score_name=row.get("score_name"),
                    )
                    for index, row in enumerate(rows[:top_k], 1)
                ]
            )
        return output


def _row(work_id, dynasty, *, suffix="0"):
    return {
        "chunk_id": f"{work_id}:{suffix}",
        "work_id": work_id,
        "text": f"{work_id} 候选",
        "title": work_id,
        "author": "作者",
        "dynasty": dynasty,
        "source_record_id": f"source:{work_id}",
    }


def test_service_composes_query_plan_fanout_fusion_and_eligibility():
    text = "此情无计可消除，才下眉头，却上心头。"
    dense = FakeChannel(
        "dense_sentence",
        "dense",
        "sentence",
        {
            text: [
                _row("current", "宋"),
                _row("fan", "宋"),
            ],
            "此情无计可消除，": [_row("fan", "宋", suffix="clause-a")],
            "才下眉头，": [_row("fan", "宋", suffix="clause-b")],
            "却上心头。": [_row("later", "明")],
        },
    )
    lexical = FakeChannel(
        "lexical_sentence",
        "lexical",
        "sentence",
        {
            text: [_row("fan", "宋")],
        },
    )

    service = TextRetrievalService(
        [dense, lexical],
        per_channel_top_k=20,
        final_top_k=5,
    )
    result = service.search(
        text,
        current_work_id="current",
        target_dynasty="宋",
    )

    assert result.status == "ok"
    assert [item.candidate.work_id for item in result.candidates] == ["fan"]
    assert result.candidates[0].chronology_status == "same_dynasty"
    assert result.candidates[0].candidate.support_count == 4
    assert {
        (item.candidate.work_id, item.reason)
        for item in result.rejected
    } == {
        ("current", "self_hit"),
        ("later", "clearly_later"),
    }
    assert dense.calls[0][1] == 20
    assert lexical.calls[0][1] == 20


def test_service_filters_before_final_top_k_cutoff():
    query = "甲。"
    channel = FakeChannel(
        "dense_sentence",
        "dense",
        "sentence",
        {
            query: [
                _row("current", "宋"),
                _row("later", "明"),
                _row("valid", "唐"),
            ],
        },
    )

    service = TextRetrievalService(
        [channel],
        per_channel_top_k=3,
        final_top_k=1,
    )
    result = service.search(
        query,
        current_work_id="current",
        target_dynasty="宋",
    )

    assert [item.candidate.work_id for item in result.candidates] == ["valid"]


def test_service_returns_no_hit_without_hiding_query_plan():
    query = "甲，乙。"
    channel = FakeChannel(
        "lexical_sentence",
        "lexical",
        "sentence",
        {},
    )

    result = TextRetrievalService([channel]).search(
        query,
        current_work_id=None,
        target_dynasty="宋",
    )

    assert result.status == "no_hit"
    assert result.candidates == ()
    assert [variant.text for variant in result.query_plan] == [
        "甲，乙。",
        "甲，",
        "乙。",
    ]


def test_service_rejects_duplicate_channel_names():
    first = FakeChannel("same", "dense", "sentence", {})
    second = FakeChannel("same", "lexical", "sentence", {})

    try:
        TextRetrievalService([first, second])
    except ValueError as exc:
        assert "name 不能重复" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_service_requires_at_least_one_channel():
    try:
        TextRetrievalService([])
    except ValueError as exc:
        assert "至少需要一个" in str(exc)
    else:
        raise AssertionError("expected ValueError")
