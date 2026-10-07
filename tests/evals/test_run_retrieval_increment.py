import json

from evals.schema import EvalInput, EvalPoemContext
from scripts.evals.run_retrieval_increment import (
    RetrievalIncrementCase,
    RetrievalTarget,
    choose_current_work_id,
    compact_tool_result,
    comparison_bucket,
    scan_work_matches,
)


def make_case() -> RetrievalIncrementCase:
    return RetrievalIncrementCase(
        id="case_one",
        tier="long_tail_probe",
        relation="adapted_quote",
        input=EvalInput(
            poem="当前句。",
            context=EvalPoemContext(
                title="当前作",
                author="今人",
                dynasty="宋",
            ),
            selection="当前句",
            question="有没有前代来源？",
        ),
        retrieval_query="当前句",
        current_match_text="当前句",
        target=RetrievalTarget(
            author="前人",
            text="前代句",
            answer_anchors=["前代句"],
        ),
        rationale="test",
    )


def test_scan_work_matches_and_choose_exact_title(tmp_path):
    works = [
        {
            "work_id": "w-current-other",
            "title": "别本",
            "author": "今人",
            "dynasty": "宋",
            "content": "当前句。",
        },
        {
            "work_id": "w-current-exact",
            "title": "当前作",
            "author": "今人",
            "dynasty": "宋",
            "content": "当前句。",
        },
        {
            "work_id": "w-target",
            "title": "前作",
            "author": "前人",
            "dynasty": "唐",
            "content": "这里有前代句。",
        },
    ]
    path = tmp_path / "works.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in works
        )
        + "\n",
        encoding="utf-8",
    )

    case = make_case()
    matches = scan_work_matches(
        work_path=path,
        cases=[case],
    )[case.id]

    assert len(matches["current"]) == 2
    assert [item["work_id"] for item in matches["target"]] == [
        "w-target"
    ]
    assert choose_current_work_id(
        case,
        matches["current"],
    ) == "w-current-exact"


def test_comparison_bucket_is_navigation_only():
    assert comparison_bucket(
        bare_signal=True,
        tool_signal=True,
        eligible_rank=3,
    ) == "base_already_knows"
    assert comparison_bucket(
        bare_signal=False,
        tool_signal=True,
        eligible_rank=40,
    ) == "tool_increment_candidate"
    assert comparison_bucket(
        bare_signal=True,
        tool_signal=False,
        eligible_rank=3,
    ) == "tool_regression_candidate"
    assert comparison_bucket(
        bare_signal=False,
        tool_signal=False,
        eligible_rank=15,
    ) == "retrieval_found_model_failed"
    assert comparison_bucket(
        bare_signal=False,
        tool_signal=False,
        eligible_rank=None,
    ) == "both_gap"


def test_compact_tool_result_does_not_expose_probe_metadata():
    result = {
        "ranking": [
            {
                "rank": 1,
                "title": "前作",
                "author": "前人",
                "dynasty": "唐",
                "support_count": 2,
                "chronology_status": "clearly_earlier",
                "best_evidence": {
                    "text": "前代句。",
                    "query": "当前句",
                    "channel": "dense_faiss_sentence",
                },
            }
        ],
        "probes": [
            {"work_id": "ground-truth-only"}
        ],
    }

    compact = compact_tool_result(result)

    assert compact["status"] == "ok"
    assert compact["candidates"][0]["author"] == "前人"
    assert "probes" not in compact
    assert "ground-truth-only" not in json.dumps(
        compact,
        ensure_ascii=False,
    )
