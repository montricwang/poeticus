"""验证整首赏析的模型调用约束，不发送真实网络请求。"""

from types import SimpleNamespace

import pytest

from backend.ai.context import PoemContext

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
    import backend.ai.model as model_module

    return model_module


def test_analyze_json_disables_reasoning_under_output_cap(monkeypatch, model):
    import json

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "translation": "清风吹拂。",
                                "glosses": [{"term": "风", "explanation": "清风"}],
                                "commentary": "写景寄情。",
                            },
                            ensure_ascii=False,
                        )
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        model,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )
    result = model.analyze_poem("风吹。", context=SAMPLE_CONTEXT)
    assert result.commentary == "写景寄情。"
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[0]["max_tokens"] <= 2048


def test_analyze_rejects_length_and_logs_no_poem(monkeypatch, model, caplog):
    def fake_create(**_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(content='{"translation":"敏感模型内容"}'),
                )
            ]
        )

    monkeypatch.setattr(
        model,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        ),
    )
    with pytest.raises(ValueError, match="未正常完成"):
        model.analyze_poem("私人原文-不要记录")
    assert "finish_reason=length" in caplog.text
    assert "私人原文" not in caplog.text
    assert "敏感模型内容" not in caplog.text
