"""Agent 流式输出回归测试，使用 Mock 模型验证 LangGraph custom 事件。"""

import json
from types import SimpleNamespace

import pytest

from poem_context import PoemContext

SAMPLE_CONTEXT = PoemContext(
    id="su-shi-huan-xi-sha-feng-juan-zhu-lian",
    title="浣溪沙·新秋",
    author="苏轼",
    dynasty="宋",
    review_status="imported_unreviewed",
)


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import intent_router
    return intent_router


def make_delta(content=None, tool_calls=None, finish_reason=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish_reason)]
    )


def make_tool_call_chunk(index, id_, name, args, finish_reason=None):
    tc = SimpleNamespace(index=index, id=id_, function=SimpleNamespace(name=name, arguments=args))
    return make_delta(content=None, tool_calls=[tc], finish_reason=finish_reason)


class MockStream:
    """可重复迭代的流式响应 Mock。"""
    def __init__(self, chunks):
        self._chunks = chunks

    def __iter__(self):
        # 每次迭代都返回新的迭代器，支持多次消费
        return iter(self._chunks)

    def close(self):
        pass


def _fake_streaming_client(agent, chunk_sequences, monkeypatch):
    """
    替换 agent.client，支持流式与非流式调用。

    chunk_sequences: list[list[chunk]]，每次流式调用对应的 chunk 列表。
    非流式调用直接返回第一个序列的最后一个 chunk 转为 message 格式。
    """
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        is_stream = kwargs.get("stream", False)
        call_idx = len(calls) - 1
        if is_stream:
            if call_idx < len(chunk_sequences):
                return MockStream(chunk_sequences[call_idx])
            # 超出预期调用次数，返回空流
            return MockStream([])
        # 非流式：返回最后一项转为 message 格式
        if call_idx < len(chunk_sequences):
            last = chunk_sequences[call_idx][-1]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=last.content if hasattr(last, 'content') else None,
                    tool_calls=last.tool_calls if hasattr(last, 'tool_calls') else None
                ))]
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=None))])

    monkeypatch.setattr(agent, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))))
    return calls


def test_streaming_direct_answer_emits_token_events(monkeypatch, agent):
    """直接回答：两个文本片段产生两个 custom token 事件，最终 reply 为拼接。"""

    chunks = [
        # 第 1 次调用（唯一调用）
        [
            make_delta(content="三"),
            make_delta(content="星", finish_reason="stop"),
        ],
    ]

    calls = _fake_streaming_client(agent, chunks, monkeypatch)

    events = list(agent.graph.stream(
        {"poem": "三星当户照绸缪。", "question": "解释三星", "stream_reply": True},
        stream_mode=["custom", "updates"],
    ))

    custom_tokens = [p.get("text") for m, p in events if m == "custom"]
    assert custom_tokens == ["三", "星"]

    final_reply = None
    for mode, payload in events:
        if mode == "updates" and isinstance(payload, dict):
            for v in payload.values():
                if isinstance(v, dict) and v.get("reply"):
                    final_reply = v["reply"]
    assert final_reply == "三星"

    assert len(calls) == 1
    assert calls[0].get("stream") is True


def test_streaming_with_tool_call_then_answer(monkeypatch, agent):
    """工具调用：流式工具参数拼接，工具执行后 Agent 继续生成流式回答。"""

    async def fake_search(query, *, provider_name, evidence_type=None):
        from backend.evidence.schema import EvidenceItem
        return [
            EvidenceItem(
                anchor=query,
                type="allusion",
                text="刘郎：此处指情郎，词人自指。",
                provider="cnkgraph",
                status="candidate",
            )
        ]

    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    chunks = [
        # 第 1 次调用：流式工具调用
        [
            make_tool_call_chunk(0, "call-1", "lookup_allusion", '{"term": '),
            make_tool_call_chunk(0, "call-1", "", '"刘郎"}', finish_reason="tool_calls"),
        ],
        # 第 2 次调用：工具返回后的流式回答
        [
            make_delta(content="刘郎指情郎"),
            make_delta(content="，词人自指。", finish_reason="stop"),
        ],
    ]

    calls = _fake_streaming_client(agent, chunks, monkeypatch)

    events = list(agent.graph.stream(
        {"poem": "测试诗", "question": "刘郎典故？", "stream_reply": True},
        stream_mode=["custom", "updates"],
    ))

    custom_tokens = [p.get("text") for m, p in events if m == "custom"]
    assert custom_tokens == ["刘郎指情郎", "，词人自指。"]

    final_reply = None
    for mode, payload in events:
        if mode == "updates" and isinstance(payload, dict):
            for v in payload.values():
                if isinstance(v, dict) and v.get("reply"):
                    final_reply = v["reply"]
    assert final_reply == "刘郎指情郎，词人自指。"

    # 验证调用次数：1 次流式工具调用 + 1 次流式回答
    assert len(calls) == 2
    assert calls[0].get("stream") is True
    assert calls[1].get("stream") is True


def test_non_streaming_invoke_still_works(monkeypatch, agent):
    """非流式回归：graph.invoke() 正常工作，不依赖 get_stream_writer。"""

    def fake_create(**kwargs):
        assert kwargs.get("stream") is not True
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="非流式回答", tool_calls=None))])

    monkeypatch.setattr(agent, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))))

    result = agent.graph.invoke(
        {"poem": "三星当户。", "question": "解释"}
    )

    assert result["reply"] == "非流式回答"
    assert result.get("tool_calls") == []


def test_sse_no_duplicate_full_reply_when_tokens_sent(monkeypatch, agent):
    """SSE 回归：已有增量 token 时，/chat/stream 不再重复发送完整回答。"""

    chunks = [
        [
            make_delta(content="第"),
            make_delta(content="一", finish_reason="stop"),
        ],
    ]

    calls = _fake_streaming_client(agent, chunks, monkeypatch)

    # 直接模拟 api.py 的 stream_graph_reply 逻辑
    received_tokens = []
    final_reply = None
    for mode, payload in agent.graph.stream(
        {"poem": "测试", "question": "测试", "stream_reply": True},
        stream_mode=["custom", "updates"],
    ):
        if mode == "custom" and isinstance(payload, dict) and payload.get("type") == "token":
            received_tokens.append(payload.get("text"))
        elif mode == "updates" and isinstance(payload, dict):
            for v in payload.values():
                if isinstance(v, dict) and v.get("reply"):
                    final_reply = v["reply"]

    assert received_tokens == ["第", "一"]
    assert final_reply == "第一"
    # 拼接后的 token 等于最终 reply，说明没有重复发送全文
    assert "".join(received_tokens) == final_reply