"""流式接口回归测试：替换 Graph，不调用真实模型。"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import api

    return api


def parse_sse(body: str):
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        if not block or block.startswith(":"):
            continue
        lines = block.split("\n")
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


def test_stream_sends_incremental_tokens_and_done(monkeypatch, api_module):
    received = []

    def fake_stream(state, stream_mode):
        received.append((state, stream_mode))
        yield "updates", {"classify_intent": {"intent": "text_reading"}}
        yield "custom", {"type": "token", "text": "三"}
        yield "custom", {"type": "token", "text": "星"}
        yield "updates", {"direct_answer": {"reply": "三星"}}

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={
            "poem": "三星当户照绸缪。",
            "question": "解释三星",
            "selection": {"text": "三星", "start": 0, "end": 2},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert parse_sse(response.text) == [
        ("token", {"text": "三"}),
        ("token", {"text": "星"}),
        ("done", {}),
    ]
    assert received == [
        ({"poem": "三星当户照绸缪。", "question": "解释三星", "selection": "三星", "stream_reply": True}, ["custom", "updates"])
    ]


@pytest.mark.parametrize("route", ["source_lookup", "clarify_user"])
def test_static_branch_emits_answer_once(monkeypatch, api_module, route):
    def fake_stream(state, stream_mode):
        yield "updates", {"classify_intent": {"intent": route}}
        yield "updates", {route: {"reply": "尚无可靠资料。"}}

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream", json={"poem": "三星当户。", "question": "出处？"}
    )
    assert parse_sse(response.text) == [
        ("token", {"text": "尚无可靠资料。"}),
        ("done", {}),
    ]


def test_failure_after_partial_keeps_tokens_and_sends_error(monkeypatch, api_module):
    def fake_stream(state, stream_mode):
        yield "custom", {"type": "token", "text": "前半句"}
        raise RuntimeError("生成中途断开")

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream", json={"poem": "三星当户。", "question": "解释"}
    )
    assert parse_sse(response.text) == [
        ("token", {"text": "前半句"}),
        ("error", {"message": "生成中途断开"}),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"poem": "  ", "question": "解释"},
        {"poem": "三星当户。", "question": "  "},
        {"poem": "三星当户。", "question": "解释", "selection": {"text": "三星", "start": 3, "end": 5}},
    ],
)
def test_stream_validation_matches_chat(monkeypatch, api_module, payload):
    def unexpected_stream(*args, **kwargs):
        pytest.fail("无效请求不应该进入 Graph")

    monkeypatch.setattr(api_module, "graph", SimpleNamespace(stream=unexpected_stream))
    response = TestClient(api_module.app).post("/chat/stream", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
