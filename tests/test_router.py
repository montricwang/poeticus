"""Graph 节点和条件边测试：用假 DeepSeek 响应，不花费 Token。"""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import intent_router

    return intent_router


@pytest.mark.parametrize(
    ("intent", "expected_step", "selection"),
    [
        ("text_reading", "direct_answer", "报"),
        ("source_lookup", "source_lookup", "三星当户"),
        ("needs_clarification", "needs_clarification", None),
    ],
)
def test_graph_routes_and_only_direct_branch_generates_answer(
    monkeypatch, router, intent, expected_step, selection
):
    model_calls = []
    answer_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps({"intent": intent, "reason": "测试分类"})
                    ),
                )
            ],
            usage=None,
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    def fake_answer(**kwargs):
        answer_calls.append(kwargs)
        return "模拟细读回答"

    monkeypatch.setattr(router, "client", fake_client)
    monkeypatch.setattr(router, "chat_about_poem", fake_answer)

    result = router.graph.invoke(
        {"poem": "萧萧乱叶报新秋。", "question": "测试问题", "selection": selection}
    )

    assert len(model_calls) == 1
    assert result["intent"] == intent
    assert result["next_step"] == expected_step
    assert isinstance(result["reply"], str) and result["reply"]

    if intent == "text_reading":
        assert result["reply"] == "模拟细读回答"
        assert answer_calls == [
            {"poem": "萧萧乱叶报新秋。", "question": "测试问题", "selection": selection}
        ]
    else:
        assert answer_calls == []


def test_classifier_rejects_unknown_intent(monkeypatch, router):
    def fake_create(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content='{"intent":"unknown","reason":"测试非法标签"}'
                    ),
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        router,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    with pytest.raises(RuntimeError, match="不符合 Schema"):
        router.classify_intent({"poem": "萧萧乱叶报新秋。", "question": "解释报字"})
