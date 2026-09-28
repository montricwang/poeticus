"""真实 LangGraph custom streaming（模型分类与答案均用假数据）。"""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import intent_router

    return intent_router


def test_direct_answer_streams_custom_events_without_double_answer(monkeypatch, router):
    model_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                content=json.dumps({"intent": "text_reading", "reason": "测试"})
            ))],
            usage=None,
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    monkeypatch.setattr(router, "client", fake_client)
    monkeypatch.setattr(router, "stream_chat_about_poem", lambda **kwargs: iter(["三", "星"]))
    events = list(router.graph.stream(
        {"poem": "三星当户。", "question": "解释", "selection": None, "stream_reply": True},
        stream_mode=["custom", "updates"],
    ))
    assert len(model_calls) == 1
    assert [(mode, payload) for mode, payload in events if mode == "custom"] == [
        ("custom", {"type": "token", "text": "三"}),
        ("custom", {"type": "token", "text": "星"}),
    ]
    assert any(
        mode == "updates" and payload.get("direct_answer", {}).get("reply") == "三星"
        for mode, payload in events
    )
