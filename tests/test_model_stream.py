"""验证 OpenAI 兼容 SDK 分片累计和未完成处理，不发送网络请求。"""

from types import SimpleNamespace

import pytest

from poem_context import PoemContext

SAMPLE_CONTEXT = PoemContext(
    id="test-poem",
    title="测试",
    author="苏轼",
    dynasty="宋",
    review_status="imported_unreviewed",
)


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import main

    return main


@pytest.mark.parametrize(
    "finish_reason,should_fail", [("stop", False), ("length", True)]
)
def test_model_stream_closes_and_checks_finish_reason(
    monkeypatch, model, finish_reason, should_fail
):
    closed = []
    calls = []

    class FakeStream:
        def __iter__(self):
            for text, reason in [("三", None), ("星", None), (None, finish_reason)]:
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content=text), finish_reason=reason
                        )
                    ]
                )

        def close(self):
            closed.append(True)

    def fake_create(**kwargs):
        calls.append(kwargs)
        return FakeStream()

    monkeypatch.setattr(
        model,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )
    if should_fail:
        with pytest.raises(ValueError, match="未正常完成"):
            list(model.stream_chat_about_poem("诗", "问题", context=SAMPLE_CONTEXT))
    else:
        assert list(
            model.stream_chat_about_poem("诗", "问题", context=SAMPLE_CONTEXT)
        ) == ["三", "星"]
    assert len(closed) == 1
    assert calls[0]["stream"] is True
    assert calls[0]["model"] == "deepseek-flash"
    assert "作品上下文" in calls[0]["messages"][1]["content"]


def test_model_stream_without_context_uses_plain_poem(monkeypatch, model):
    calls = []

    class FakeStream:
        def __iter__(self):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="三"), finish_reason=None
                    )
                ]
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None), finish_reason="stop"
                    )
                ]
            )

        def close(self):
            pass

    def fake_create(**kwargs):
        calls.append(kwargs)
        return FakeStream()

    monkeypatch.setattr(
        model,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )

    assert list(model.stream_chat_about_poem("诗", "问题")) == ["三"]
    assert "作品上下文" not in calls[0]["messages"][1]["content"]



def test_analyze_json_disables_reasoning_under_output_cap(monkeypatch, model):
    import json

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=json.dumps({
                "translation": "清风吹拂。",
                "glosses": [{"term": "风", "explanation": "清风"}],
                "commentary": "写景寄情。",
            }, ensure_ascii=False)),
        )])

    monkeypatch.setattr(
        model, "client",
        SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )),
    )
    result = model.analyze_poem("风吹。", context=SAMPLE_CONTEXT)
    assert result.commentary == "写景寄情。"
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[0]["max_tokens"] <= 2048


def test_analyze_rejects_length_and_logs_no_poem(monkeypatch, model, caplog):
    def fake_create(**_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="length",
            message=SimpleNamespace(content='{"translation":"secret poem"}'),
        )])

    monkeypatch.setattr(
        model, "client",
        SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create)
        )),
    )
    with pytest.raises(ValueError, match="未正常完成"):
        model.analyze_poem("私人原文-不要记录")
    assert "finish_reason=length" in caplog.text
    assert "私人原文" not in caplog.text
    assert "secret poem" not in caplog.text
