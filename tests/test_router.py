"""测试 Agent 图的上下文与工具守卫回归，不调用真实 API。"""

from types import SimpleNamespace

import pytest

from backend.ai.context import PoemContext, format_poem_context

SAMPLE_CONTEXT = PoemContext(
    id="su-shi-huan-xi-sha-feng-juan-zhu-lian",
    title="浣溪沙·新秋",
    author="苏轼",
    dynasty="宋",
    review_status="imported_unreviewed",
)


@pytest.fixture
def graph_module(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    import backend.ai.graph as graph_module

    return graph_module


def _fake_client(fake_create):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )


def _text_response(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))
        ]
    )


def _tool_call_response(call_id, name, arguments):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id=call_id,
                            type="function",
                            function=SimpleNamespace(
                                name=name,
                                arguments=arguments,
                            ),
                        )
                    ],
                )
            )
        ]
    )


def _user_message(model_calls):
    return model_calls[0]["messages"][1]["content"]


def test_graph_sends_poem_context_to_model(monkeypatch, graph_module):
    """有作品元数据时，模型收到对应上下文。"""

    model_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return _text_response("模拟细读回答")

    monkeypatch.setattr(graph_module, "client", _fake_client(fake_create))

    result = graph_module.graph.invoke(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": None,
            "context": SAMPLE_CONTEXT,
        }
    )

    assert result["reply"] == "模拟细读回答"

    user_content = _user_message(model_calls)
    assert format_poem_context(SAMPLE_CONTEXT) in user_content
    assert "作者：苏轼" in user_content
    assert "作品上下文" in user_content
    assert "imported_unreviewed" not in user_content


def test_graph_answers_request_without_context(monkeypatch, graph_module):
    """作品元数据是可选字段；缺省时仍可正常回答。"""

    model_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)
        return _text_response("模拟细读回答")

    monkeypatch.setattr(graph_module, "client", _fake_client(fake_create))

    result = graph_module.graph.invoke(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "解释报字",
            "selection": None,
        }
    )

    assert result["reply"] == "模拟细读回答"
    assert "作品上下文" not in _user_message(model_calls)


def test_unknown_tool_is_not_executed(monkeypatch, graph_module):
    """模型伪造未注册工具时，只返回错误结果，不触发检索。"""

    model_calls = []
    search_calls = []

    def fake_create(**kwargs):
        model_calls.append(kwargs)

        if len(model_calls) == 1:
            return _tool_call_response(
                "call-1",
                "lookup_unknown",
                '{"term": "刘郎"}',
            )

        return _text_response("没有可用的检索工具，只能凭已有知识回答。")

    async def fake_search(query, *, provider_name, evidence_type=None):
        search_calls.append(
            {
                "query": query,
                "provider_name": provider_name,
                "evidence_type": evidence_type,
            }
        )

    monkeypatch.setattr(graph_module, "client", _fake_client(fake_create))
    monkeypatch.setattr(graph_module.evidence_service, "search", fake_search)

    result = graph_module.graph.invoke(
        {
            "poem": "萧萧乱叶报新秋。",
            "question": "刘郎有什么典故？",
            "selection": None,
        }
    )

    assert search_calls == []

    assert len(model_calls) == 2
    tool_messages = [
        message
        for message in model_calls[1]["messages"]
        if message.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    assert "未知工具" in tool_messages[0]["content"]

    assert result["reply"] == "没有可用的检索工具，只能凭已有知识回答。"


def test_format_poem_context_notes_only_imported_unreviewed():
    assert format_poem_context(None) == ""

    unreviewed = format_poem_context(SAMPLE_CONTEXT)
    assert "题名：浣溪沙·新秋" in unreviewed
    assert "作者：苏轼" in unreviewed
    assert "时代：宋" in unreviewed
    assert "imported_unreviewed" not in unreviewed
    assert "尚未完成全面校勘" in unreviewed

    reviewed = format_poem_context(
        PoemContext(
            id="other-work",
            title="其他作品",
            author="某某",
            dynasty="唐",
            review_status="reviewed",
        )
    )
    assert "题名：其他作品" in reviewed
    assert "作者：某某" in reviewed
    assert "时代：唐" in reviewed
    assert "尚未完成全面校勘" not in reviewed
