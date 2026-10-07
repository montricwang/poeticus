import pytest

from backend.retrieval.query_strategy import build_query_plan


def _levels(variant):
    return [origin.level for origin in variant.origins]


def test_build_query_plan_emits_passage_sentence_and_clause_queries():
    text = "此情无计可消除，才下眉头，却上心头。后句。"

    plan = build_query_plan(text)

    assert [variant.text for variant in plan] == [
        text,
        "此情无计可消除，才下眉头，却上心头。",
        "后句。",
        "此情无计可消除，",
        "才下眉头，",
        "却上心头。",
    ]
    assert _levels(plan[0]) == ["passage"]
    assert _levels(plan[1]) == ["sentence"]
    assert _levels(plan[2]) == ["sentence", "clause"]


def test_build_query_plan_coalesces_identical_text_across_levels():
    plan = build_query_plan("片片轻鸥落晚沙。")

    assert len(plan) == 1
    assert plan[0].text == "片片轻鸥落晚沙。"
    assert _levels(plan[0]) == ["passage", "sentence", "clause"]


def test_build_query_plan_coalesces_repeated_query_text_but_keeps_origins():
    plan = build_query_plan("山月。山月。")

    assert [variant.text for variant in plan] == ["山月。山月。", "山月。"]
    repeated = plan[1]
    assert _levels(repeated) == ["sentence", "sentence", "clause", "clause"]
    assert [(origin.start, origin.end) for origin in repeated.origins] == [
        (0, 3),
        (3, 6),
        (0, 3),
        (3, 6),
    ]


def test_build_query_plan_preserves_trimmed_passage_offsets():
    text = "  甲，乙。  "

    plan = build_query_plan(text)

    assert plan[0].text == "甲，乙。"
    assert (plan[0].origins[0].start, plan[0].origins[0].end) == (2, 6)


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_build_query_plan_rejects_blank_text(text):
    with pytest.raises(ValueError, match="空白"):
        build_query_plan(text)
