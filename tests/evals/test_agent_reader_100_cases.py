"""Structural safeguards for the draft 100-question reader evaluation dataset.

These tests do not claim literary correctness or verify source editions.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evals.schema import EvalInput
from scripts.evals.render_agent_reader_questions import render

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "evals" / "agent_reader_100_cases.json"
REVIEW_PATH = ROOT / "evals" / "agent_reader_100_review.md"


def bank() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def test_reader_bank_has_100_unique_natural_questions_at_three_levels():
    data = bank()
    cases = data["cases"]
    assert data["schema_version"] == "1"
    assert data["status"] == "draft"
    assert len(cases) == 100
    assert [x["id"] for x in cases] == [f"reader_{n:03d}" for n in range(1, 101)]
    assert Counter(x["level"] for x in cases) == {
        "beginner": 40, "intermediate": 35, "advanced": 25,
    }
    assert Counter(x["split"] for x in cases) == {
        "development": 80, "reserved_for_review": 20,
    }
    questions = [x["input"]["question"] for x in cases]
    assert len(set(questions)) == 100
    assert all(q.endswith("？") and len(q) > 10 for q in questions)
    assert len({c["topic"] for c in cases}) >= 15
    assert all(c["review_status"] == "draft_unverified" for c in cases)
    assert all(c["review_focus"] for c in cases)


def test_reader_questions_do_not_inject_tool_routes_or_unverified_gold():
    data = bank()
    forbidden = {"tool_policy", "expected_tools", "expected", "gold_answer", "reference_targets"}
    for case in data["cases"]:
        assert not (set(case) & forbidden)
        assert not (set(case["input"]) & forbidden)
        assert set(case["input"]).issubset({"question", "fixture_id", "selection"})


def test_every_selected_span_is_in_its_attached_source_text():
    data = bank()
    fixtures = data["fixtures"]
    valid_fixtures = 0
    for fixture in fixtures.values():
        assert fixture["text_scope"] in {"full_candidate", "full_from_existing_seed", "excerpt"}
        assert fixture["text_review_status"] == "pending_independent_collation"
        assert len(fixture["poem"]) > 7
        assert fixture["title"] and fixture["author"]
    for case in data["cases"]:
        inp = case["input"]
        if "fixture_id" not in inp:
            assert "selection" not in inp
            continue
        valid_fixtures += 1
        fixture = fixtures[inp["fixture_id"]]
        # Uses existing Poeticus EvalInput validation, not a parallel new poem schema.
        model = EvalInput.model_validate({
            "poem": fixture["poem"],
            "context": {
                "title": fixture["title"],
                "author": fixture["author"],
                "dynasty": fixture["dynasty"],
            },
            "selection": inp.get("selection"),
            "question": inp["question"],
        })
        assert model.question == inp["question"]
    assert 40 <= valid_fixtures <= 90


def test_question_bank_preserves_simple_prompts_and_exploratory_coverage():
    cases = bank()["cases"]
    assert any("古代类书" in x["input"]["question"] for x in cases)
    assert any("年谱" in x["input"]["question"] for x in cases)
    assert any("典故" in x["input"]["question"] for x in cases)
    assert any("词谱" in x["input"]["question"] for x in cases)
    assert any("有没有" in x["input"]["question"] for x in cases)
    assert any(x["topic"] == "字词训诂" for x in cases[:40])
    assert any(x["topic"] == "研究方法" for x in cases[75:])


def test_human_review_sheet_exactly_matches_source_json():
    assert REVIEW_PATH.read_text(encoding="utf-8") == render(bank())


def test_runner_uses_real_fixture_or_explicitly_empty_standalone_context():
    from scripts.evals.run_agent_reader_100 import build_state

    data = bank()
    contextual = next(c for c in data["cases"] if "fixture_id" in c["input"])
    standalone = next(c for c in data["cases"] if "fixture_id" not in c["input"])
    contextual_state = build_state(contextual, data["fixtures"])
    assert contextual_state["poem"]
    assert contextual_state["context"].title
    assert contextual_state["selection"] == contextual["input"].get("selection")
    assert contextual_state["question"] == contextual["input"]["question"]
    independent_state = build_state(standalone, data["fixtures"])
    assert independent_state["poem"] == ""
    assert independent_state["context"] is None
    assert independent_state["selection"] is None
    assert independent_state["question"] == standalone["input"]["question"]
