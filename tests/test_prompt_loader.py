"""测试 Prompt 模板的注册、加载和组合。"""

import pytest

from backend.ai.prompt_loader import load_prompt, compose_prompt


@pytest.mark.parametrize(
    "name",
    [
        "output_style",
        "agent_decide",
        "analyze_poem",
        "chat",
        "evidence_answer",
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


def test_agent_decide_prompt_contains_tool_selection_principles():
    prompt = load_prompt("agent_decide")

    assert "工具使用原则" in prompt
    assert "只能调用真正适合当前问题的工具" in prompt
    assert "选区与问题中出现不同对象时" in prompt
    assert "从哪里来、出自哪里、是什么典故" in prompt
    assert "最短且有辨识度的典故锚点" in prompt
    assert "全文相似检索" in prompt


def test_output_style_contains_quote_rules():
    prompt = load_prompt("output_style")

    assert "「」" in prompt
    assert "『』" in prompt
