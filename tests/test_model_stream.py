"""验证 OpenAI 兼容 SDK 分片累计和未完成处理，不发送网络请求。"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import main

    return main


@pytest.mark.parametrize("finish_reason,should_fail", [("stop", False), ("length", True)])
def test_model_stream_closes_and_checks_finish_reason(monkeypatch, model, finish_reason, should_fail):
    closed = []
    calls = []

    class FakeStream:
        def __iter__(self):
            for text, reason in [("三", None), ("星", None), (None, finish_reason)]:
                yield SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=text), finish_reason=reason
                )])
        def close(self):
            closed.append(True)

    def fake_create(**kwargs):
        calls.append(kwargs)
        return FakeStream()

    monkeypatch.setattr(model, "client", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    ))
    if should_fail:
        with pytest.raises(ValueError, match="未正常完成"):
            list(model.stream_chat_about_poem("诗", "问题"))
    else:
        assert list(model.stream_chat_about_poem("诗", "问题")) == ["三", "星"]
    assert len(closed) == 1
    assert calls[0]["stream"] is True
    assert calls[0]["model"] == "deepseek-flash"
