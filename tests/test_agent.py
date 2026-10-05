"""Agent 工具调用流程的离线测试，不调用真实模型或 CNKGraph。"""

import json
from types import SimpleNamespace

import pytest

from backend.evidence.schema import EvidenceItem

POEM = (
    "风卷珠帘自上钩，萧萧乱叶报新秋。"
    "独携纤手上高楼。"
    "缺月向人舒窈窕，三星当户照绸缪。"
    "香生雾縠见纤柔。"
)


@pytest.fixture
def agent(monkeypatch):
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


def test_model_answers_author_question_without_tools(monkeypatch, agent):
    create_calls = []
    search_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        return _text_response("这首词大约作于某个秋天。")

    async def fake_search(query, *, provider_name, evidence_type=None):
        search_calls.append(query)
        return []

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    result = agent.graph.invoke(
        {
            "poem": POEM,
            "question": "作者是什么时候写的？",
            "selection": None,
        }
    )

    assert result["reply"] == "这首词大约作于某个秋天。"
    assert result.get("tool_calls") == []
    assert result.get("evidences") is None
    assert len(create_calls) == 1
    assert search_calls == []


def test_model_answers_identity_question_without_tools(monkeypatch, agent):
    create_calls = []
    search_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        return _text_response("这里不是指小妾，而是指同游的伴侣。")

    async def fake_search(query, *, provider_name, evidence_type=None):
        search_calls.append(query)
        return []

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    result = agent.graph.invoke(
        {
            "poem": POEM,
            "question": "这里是作者跟自己小妾么？",
            "selection": "独携纤手上高楼",
        }
    )

    assert result["reply"] == "这里不是指小妾，而是指同游的伴侣。"
    assert result.get("tool_calls") == []
    assert len(create_calls) == 1
    assert search_calls == []


def test_tool_call_queries_requested_term_and_returns_final_reply(
    monkeypatch,
    agent,
):
    create_calls = []
    search_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        if len(create_calls) == 1:
            return _tool_call_response(
                "call-1",
                "lookup_allusion",
                json.dumps({"term": "刘郎"}, ensure_ascii=False),
            )
        return _text_response("刘郎在此指情郎，是词人的自指。")

    async def fake_search(query, *, provider_name, evidence_type=None):
        search_calls.append(
            {
                "query": query,
                "provider_name": provider_name,
                "evidence_type": evidence_type,
            }
        )
        return [
            EvidenceItem(
                anchor=query,
                type="allusion",
                text="刘郎：此处指情郎，词人自指。",
                provider="cnkgraph",
                status="candidate",
            )
        ]

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    result = agent.graph.invoke(
        {
            "poem": POEM,
            "question": "这里的刘郎是谁？",
            "selection": "独携纤手上高楼",
        }
    )

    assert search_calls == [
        {
            "query": "刘郎",
            "provider_name": "cnkgraph",
            "evidence_type": "allusion",
        }
    ]
    assert result["reply"] == "刘郎在此指情郎，是词人的自指。"
    assert len(create_calls) == 2

    tool_messages = [
        message
        for message in create_calls[1]["messages"]
        if message.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    assert "刘郎：此处指情郎" in tool_messages[0]["content"]


def test_agent_includes_conversation_history_before_current_user(
    monkeypatch,
    agent,
):
    create_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        return _text_response("这里的“它”仍然指三星当户。")

    monkeypatch.setattr(
        agent,
        "client",
        _fake_client(fake_create),
    )

    result = agent.graph.invoke(
        {
            "poem": "三星当户照绸缪。",
            "question": "那它和绸缪有什么关系？",
            "selection": None,
            "history": [
                {
                    "role": "user",
                    "content": "三星当户是什么意思？",
                },
                {
                    "role": "assistant",
                    "content": "这里化用了《诗经·绸缪》。",
                },
            ],
        }
    )

    assert result["reply"] == "这里的“它”仍然指三星当户。"
    assert len(create_calls) == 1

    messages = create_calls[0]["messages"]

    assert messages[0]["role"] == "system"

    assert messages[1] == {
        "role": "user",
        "content": "三星当户是什么意思？",
    }
    assert messages[2] == {
        "role": "assistant",
        "content": "这里化用了《诗经·绸缪》。",
    }

    assert messages[3]["role"] == "user"
    assert "那它和绸缪有什么关系？" in messages[3]["content"]



def test_external_tool_payload_is_bounded_before_return_to_model(monkeypatch, agent):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _tool_call_response(
                "cap-1", "lookup_allusion", json.dumps({"term": "刘郎"})
            )
        return _text_response("证据应当节选。")

    async def fake_search(query, *, provider_name, evidence_type=None):
        return [
            EvidenceItem(
                anchor=query, type="allusion",
                text="甲" * 5000, provider="cnkgraph", status="candidate"
            )
            for _ in range(6)
        ]

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)
    agent.graph.invoke({"poem": POEM, "question": "请查典故", "selection": None})

    tool_msg = next(
        m for m in calls[1]["messages"] if m.get("role") == "tool"
    )
    data = json.loads(tool_msg["content"])
    assert len(data["evidences"]) == 3
    assert all(len(item["text"]) == 1600 for item in data["evidences"])
