"""The consolidated Serving benchmark preserves its cold-query diagnostics."""
import json

from backend.retrieval.serving import ServingCandidate, ServingSearchResult
from scripts.retrieval.benchmark_serving import (
    BenchmarkCase,
    resolve_current_work_ids,
    run_uncached_cases,
)


def cases() -> list[BenchmarkCase]:
    return [{
        "id": "case-one",
        "retrieval_query": "轻鸥落晚沙",
        "current_match_text": "轻鸥落晚沙",
        "input": {
            "poem": "轻鸥落晚沙。",
            "context": {"author": "陆游", "dynasty": "宋"},
        },
        "target": {"author": "杜甫", "text": "轻鸥下急湍"},
    }]


def fake_timing() -> dict[str, object]:
    return {
        "current_alias_lookup_ms": 0.0,
        "orchestration_ms": 1.0,
        "total_ms": 9.0,
        "channels": {
            "dense_sentence": {
                "encode_ms": 4.0, "ann_ms": 1.0, "metadata_ms": 0.5,
            },
            "dense_clause": {
                "encode_ms": 0.0, "ann_ms": 1.0, "metadata_ms": 0.5,
            },
            "bm25_sentence": {"total_ms": 1.0},
        },
    }


class StubEncoder:
    def __init__(self):
        self.cache_clears = 0

    def clear_cache(self):
        self.cache_clears += 1


class StubRuntime:
    def __init__(self):
        self.encoder = StubEncoder()
        self.calls = []

    def search(self, text: str, **kwargs: object) -> ServingSearchResult:
        self.calls.append((text, kwargs))
        return ServingSearchResult(
            status="ok",
            query=text,
            timings_ms=fake_timing(),
            current_work_aliases=(),
            candidates=(ServingCandidate(
                rank=1, work_id="synthetic-dufu", author="杜甫",
                title="小寒食舟中作", text="片片轻鸥下急湍",
                dynasty="唐", source_record_id="synthetic-source",
                chronology_status="clearly_earlier", support_count=1,
            ),),
        )


def test_resolve_current_work_ids_by_author_and_excerpt(tmp_path):
    path = tmp_path / "works.jsonl"
    records = [
        {"work_id": "w1", "author": "陆游", "content": "两句轻鸥落晚沙。"},
        {"work_id": "w2", "author": "杜甫", "content": "轻鸥落晚沙"},
        {"work_id": "w3", "author": "陆游", "content": "其他诗句。"},
        {"work_id": "w4", "author": "陆游", "content": "轻鸥落晚沙。"},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n",
        encoding="utf-8",
    )
    assert resolve_current_work_ids(path, cases()) == {
        "case-one": {"w1", "w4"},
    }


def test_uncached_cases_clear_cache_and_exclude_all_current_work_ids(tmp_path):
    path = tmp_path / "works.jsonl"
    path.write_text(
        json.dumps({"work_id": "w1", "author": "陆游",
                    "content": "轻鸥落晚沙"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    runtime = StubRuntime()
    result = run_uncached_cases(runtime, cases(), path, top_k=8)
    assert runtime.encoder.cache_clears == 1
    assert runtime.calls[0][1]["current_work_ids"] == {"w1"}
    assert runtime.calls[0][1]["final_top_k"] == 8
    assert result[0]["resolved_current_work_ids"] == ["w1"]
    assert result[0]["target_visible"] is True
    assert result[0]["timings"]["sentence_encode_ms"] == 4.0
