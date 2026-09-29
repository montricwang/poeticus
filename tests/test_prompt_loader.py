"""测试 Prompt 模板的注册、加载和组合。"""

import pytest

from prompt_loader import load_prompt, compose_prompt


@pytest.mark.parametrize(
    "name",
    [
        "output_style",
        "evidence_answer",
        "analyze_poem",
        "chat",
        "classify_intent",
    ],
)
def test_registered_prompts_are_not_empty(name):
    assert load_prompt(name).strip()


def test_unknown_prompt_is_rejected():
    with pytest.raises(ValueError, match="未知 Prompt"):
        load_prompt("nonexistent")


def test_compose_prompt_preserves_order():
    result = compose_prompt("chat", "output_style")

    assert result == (load_prompt("chat") + "\n\n" + load_prompt("output_style"))


def test_classifier_prompt_contains_all_intents():
    prompt = load_prompt("classify_intent")

    assert "text_reading" in prompt
    assert "source_lookup" in prompt
    assert "needs_clarification" in prompt


def test_output_style_contains_quote_rules():
    prompt = load_prompt("output_style")

    assert "「」" in prompt
    assert "『』" in prompt
