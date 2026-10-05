"""流式接口回归测试：替换 Graph，不调用真实模型。"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from poem_context import PoemContext

SAMPLE_CONTEXT = {
    "id": "su-shi-huan-xi-sha-feng-juan-zhu-lian",
    "title": "浣溪沙·新秋",
    "author": "苏轼",
    "dynasty": "宋",
    "review_status": "imported_unreviewed",
}


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
        yield "custom", {"type": "token", "text": "三"}
        yield "custom", {"type": "token", "text": "星"}
        yield (
            "updates",
            {
                "agent": {
                    "reply": "三星",
                    "tool_calls": [],
                }
            },
        )

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={
            "poem": "三星当户照绸缪。",
            "question": "解释三星",
            "selection": {"text": "三星", "start": 0, "end": 2},
            "context": SAMPLE_CONTEXT,
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
    assert len(received) == 1
    state, stream_mode = received[0]
    assert stream_mode == ["custom", "updates"]
    assert state["poem"] == "三星当户照绸缪。"
    assert state["question"] == "解释三星"
    assert state["selection"] == "三星"
    assert state["stream_reply"] is True
    assert isinstance(state["context"], PoemContext)
    assert state["context"].model_dump() == SAMPLE_CONTEXT


def test_stream_accepts_request_without_context(monkeypatch, api_module):
    received = []

    def fake_stream(state, stream_mode):
        received.append(state)
        yield (
            "updates",
            {
                "agent": {
                    "reply": "旧请求仍可用。",
                    "tool_calls": [],
                }
            },
        )

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={"poem": "三星当户。", "question": "解释"},
    )
    assert response.status_code == 200
    assert parse_sse(response.text) == [
        ("token", {"text": "旧请求仍可用。"}),
        ("done", {}),
    ]
    assert received[0]["context"] is None


def test_tool_round_emits_final_answer_once(monkeypatch, api_module):
    """Agent 调用工具后，只补发一次最终回答。"""

    def fake_stream(state, stream_mode):
        # 第一轮 Agent 决定调用工具。
        yield (
            "updates",
            {
                "agent": {
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "lookup_allusion",
                            "arguments": '{"term": "三星当户"}',
                        }
                    ]
                }
            },
        )

        # 工具返回查询结果。
        yield (
            "updates",
            {
                "tools": {
                    "tool_results": [
                        {
                            "id": "call-1",
                            "content": '{"status": "no_hit", "evidences": []}',
                        }
                    ]
                }
            },
        )

        # 第二轮 Agent 返回最终回答。
        # 这里故意不发送 custom token，以测试 API 的全文补发逻辑。
        yield (
            "updates",
            {
                "agent": {
                    "reply": "尚无可靠资料。",
                    "tool_calls": [],
                }
            },
        )

    monkeypatch.setattr("backend.api.chat.graph",
        SimpleNamespace(stream=fake_stream),
    )

    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={
            "poem": "三星当户。",
            "question": "出处？",
            "context": SAMPLE_CONTEXT,
        },
    )

    assert response.status_code == 200
    assert parse_sse(response.text) == [
        ("token", {"text": "尚无可靠资料。"}),
        ("done", {}),
    ]


def test_failure_after_partial_keeps_tokens_and_sends_error(monkeypatch, api_module):
    def fake_stream(state, stream_mode):
        yield "custom", {"type": "token", "text": "前半句"}
        raise RuntimeError("生成中途断开")

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(stream=fake_stream))
    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={
            "poem": "三星当户。",
            "question": "解释",
            "context": SAMPLE_CONTEXT,
        },
    )
    assert parse_sse(response.text) == [
        ("token", {"text": "前半句"}),
        ("error", {"message": "生成中断，请稍后重试"}),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"poem": "  ", "question": "解释", "context": SAMPLE_CONTEXT},
        {"poem": "三星当户。", "question": "  ", "context": SAMPLE_CONTEXT},
        {
            "poem": "三星当户。",
            "question": "解释",
            "selection": {"text": "三星", "start": 3, "end": 5},
            "context": SAMPLE_CONTEXT,
        },
    ],
)
def test_stream_validation_matches_chat(monkeypatch, api_module, payload):
    def unexpected_stream(*args, **kwargs):
        pytest.fail("无效请求不应该进入 Graph")

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(stream=unexpected_stream))
    response = TestClient(api_module.app).post("/chat/stream", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")


def test_stream_passes_history_to_graph(monkeypatch, api_module):
    received = []

    def fake_stream(state, stream_mode):
        received.append(state)
        yield (
            "updates",
            {
                "agent": {
                    "reply": "这是结合上一轮的回答。",
                    "tool_calls": [],
                }
            },
        )

    monkeypatch.setattr("backend.api.chat.graph",
        SimpleNamespace(stream=fake_stream),
    )

    response = TestClient(api_module.app).post(
        "/chat/stream",
        json={
            "poem": "三星当户照绸缪。",
            "question": "那第二点呢？",
            "history": [
                {
                    "role": "user",
                    "content": "三星是什么意思？",
                },
                {
                    "role": "assistant",
                    "content": "这里有两种主要解释。",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert received[0]["history"] == [
        {
            "role": "user",
            "content": "三星是什么意思？",
        },
        {
            "role": "assistant",
            "content": "这里有两种主要解释。",
        },
    ]
