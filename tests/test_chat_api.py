""" /chat 回归测试：在 API 边界替换 Graph，不调用真实模型。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module(monkeypatch):
    # 在导入 main.py 之前提供无效但格式合法的测试密钥。
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import api

    return api


@pytest.fixture
def client(api_module):
    return TestClient(api_module.app)


@pytest.mark.parametrize(
    ("intent", "reply"),
    [
        ("text_reading", "这个字在这里使用了拟人的写法。"),
        ("source_lookup", "需要先核对文献出处。"),
        ("needs_clarification", "你具体指哪个词？"),
    ],
)
def test_chat_returns_graph_reply_without_changing_frontend_contract(
    monkeypatch, api_module, client, intent, reply
):
    received = []

    def fake_invoke(state):
        received.append(state)
        return {"intent": intent, "reply": reply}

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(invoke=fake_invoke))
    response = client.post(
        "/chat",
        json={
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": {"text": "报", "start": 4, "end": 5},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"answer": reply}
    assert received == [
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": "报",
        }
    ]


def test_chat_graph_failure_returns_502(monkeypatch, api_module, client):
    def fake_failure(state):
        raise RuntimeError("意图识别 API 调用失败")

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(invoke=fake_failure))
    response = client.post(
        "/chat",
        json={"poem": "萧萧乱叶报新秋。", "question": "解释报字"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "意图识别 API 调用失败"}


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"poem": "   ", "question": "解释报字"}, "诗歌原文不能为空"),
        ({"poem": "萧萧乱叶报新秋。", "question": "  "}, "问题不能为空"),
        (
            {
                "poem": "萧萧乱叶报新秋。",
                "question": "解释报字",
                "selection": {"text": "秋", "start": 4, "end": 5},
            },
            "引用位置与原文不一致",
        ),
    ],
)
def test_chat_rejects_invalid_requests_before_running_graph(
    monkeypatch, api_module, client, payload, detail
):
    def unexpected_invoke(state):
        pytest.fail("无效请求不应该调用 Graph")

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(invoke=unexpected_invoke))
    response = client.post("/chat", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": detail}
