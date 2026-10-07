import json

from evals.schema import EvalInput, EvalPoemContext
from scripts.evals.run_retrieval_increment import (
    RetrievalIncrementCase,
    RetrievalTarget,
    choose_current_work_id,
    heuristic_bucket,
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


def test_heuristic_bucket_is_navigation_only():
    assert heuristic_bucket(
        base_signal=True,
        eligible_rank=3,
    ) == "both_strong"
    assert heuristic_bucket(
        base_signal=True,
        eligible_rank=40,
    ) == "base_model_stronger"
    assert heuristic_bucket(
        base_signal=False,
        eligible_rank=4,
    ) == "retrieval_increment_candidate"
    assert heuristic_bucket(
        base_signal=False,
        eligible_rank=15,
    ) == "retrieval_possible_increment"
    assert heuristic_bucket(
        base_signal=False,
        eligible_rank=None,
    ) == "both_gap"
