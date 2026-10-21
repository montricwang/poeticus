"""互文 Skill 对照脚本的离线契约测试；不请求模型。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.evals import run_intertext_skill_ab as ab


def test_intertext_dataset_has_six_balanced_categories():
    data = json.loads(ab.DEFAULT_DATASET.read_text(encoding="utf-8"))
    fixtures = json.loads((ab.ROOT / data["fixture_source"]).read_text(encoding="utf-8"))
    ab.validate_dataset(data, fixtures)
    assert len([x for x in data["cases"] if x["split"] == "pilot"]) == 5
    assert len(set(x["id"] for x in data["cases"])) == 30
    assert all(x["review_status"] == "draft_fact_check_pending" for x in data["cases"])


def test_variant_lengths_and_no_source_cards_in_baseline():
    assert ab.skill_body("D") == ""
    a = ab.skill_body("A")
    b = ab.skill_body("B")
    c = ab.skill_body("C")
    assert 0 < len(a) < len(b) < len(c)
    assert "参考资料：examples.md" in c
    assert "【本轮加载" not in a


def test_injected_prompt_only_changes_agent_prompt_and_restores_on_error():
    def original(*names: str) -> str:
        return "/".join(names)
    module = SimpleNamespace(compose_prompt=original)
    with pytest.raises(RuntimeError, match="intentional"):
        with ab.injected_prompt(module, "方法一"):
            assert module.compose_prompt("agent_decide", "output_style").endswith("方法一")
            assert module.compose_prompt("chat", "output_style") == "chat/output_style"
            raise RuntimeError("intentional")
    assert module.compose_prompt is original


def test_trial_shuffle_is_deterministic_and_all_arms_present():
    cases = [{"id": "one"}, {"id": "two"}]
    first = [(x["id"], arm) for x, arm in ab.ordered_trials(cases, ab.VARIANTS)]
    second = [(x["id"], arm) for x, arm in ab.ordered_trials(cases, ab.VARIANTS)]
    assert first == second
    for name in ("one", "two"):
        assert {arm for case, arm in first if case == name} == set(ab.VARIANTS)


def test_checkpoint_signature_guards_against_mixing_runs(tmp_path: Path):
    output = tmp_path / "run.jsonl"
    record = {"run_signature": "abc", "case_id": "q1", "variant": "A", "status": "ok"}
    ab.append_record(output, record)
    assert ab.load_completed(output, "abc") == {("q1", "A"): record}
    with pytest.raises(ValueError, match="configuration changed"):
        ab.load_completed(output, "changed")


def test_blind_answer_export_keeps_arm_key_separate(tmp_path: Path):
    output = tmp_path / "run.jsonl"
    ab.append_record(output, {
        "run_signature": "sig", "case_id": "q1", "variant": "A",
        "status": "ok", "answer": "比较文本具体证据",
    })
    ab.append_record(output, {
        "run_signature": "sig", "case_id": "q1", "variant": "D",
        "status": "error",
    })
    ab.export_blind(output, "sig")
    answers = json.loads((tmp_path / "run_blind.json").read_text(encoding="utf-8"))
    keys = json.loads((tmp_path / "run_blind_key.json").read_text(encoding="utf-8"))
    assert len(answers) == len(keys) == 1
    assert "variant" not in answers[0]
    assert keys[0]["variant"] == "A"
