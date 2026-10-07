"""Agent 工具调用流程的离线测试，不调用真实模型或 CNKGraph。"""

import json
from types import SimpleNamespace

import pytest

from backend.evidence.schema import EvidenceItem
from backend.retrieval.client import (
    RetrievalCandidate,
    RetrievalSearchResponse,
)

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

def test_tool_budget_exhaustion_disables_tools_and_hides_protocol(
    monkeypatch,
    agent,
):
    """预算耗尽后只允许最终正文，内部 DSML 协议不能泄漏给用户。"""

    create_calls = []
    search_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)

        if len(create_calls) == 1:
            return _tool_call_response(
                "call-1",
                "lookup_allusion",
                json.dumps({"term": "片片轻鸥"}, ensure_ascii=False),
            )

        if len(create_calls) == 2:
            return _tool_call_response(
                "call-2",
                "lookup_allusion",
                json.dumps({"term": "轻鸥"}, ensure_ascii=False),
            )

        return _text_response(
            '<｜｜DSML｜｜ calls>'
            '<｜｜DSML｜｜ invoke name="lookup_allusion">'
            '</｜｜DSML｜｜ invoke>'
            '</｜｜DSML｜｜ calls>'
        )

    async def fake_search(query, *, provider_name, evidence_type=None):
        search_calls.append(query)
        return []

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    result = agent.graph.invoke(
        {
            "poem": "片片轻鸥落晚沙。",
            "question": "这句改用了谁的诗？",
            "selection": None,
        }
    )

    assert search_calls == ["片片轻鸥", "轻鸥"]
    assert result["tool_count"] == 2
    assert len(result["tool_results"]) == 2
    assert result["reply"] == agent._TOOL_PROTOCOL_FALLBACK

    # 第三轮只是根据已有结果收束答案，不再把 Tool Schema 暴露给模型。
    assert "tools" not in create_calls[2]
    assert "tool_choice" not in create_calls[2]
    assert agent._FINAL_AFTER_TOOL_BUDGET in (
        create_calls[2]["messages"][0]["content"]
    )

def test_tool_contracts_separate_allusion_and_reference_search(agent):
    allusion_tool = agent.TOOLS[0]["function"]
    reference_tool = agent.TOOLS[1]["function"]

    assert allusion_tool["name"] == "lookup_allusion"
    assert "人物故事" in allusion_tool["description"]
    assert "借了谁哪一句诗" in allusion_tool["description"]
    assert "整句诗文的全文相似检索" in allusion_tool["description"]

    term = allusion_tool["parameters"]["properties"]["term"]
    assert "最短且有辨识度的锚点" in term["description"]

    assert reference_tool["name"] == "lookup_reference"
    assert "前代诗文" in reference_tool["description"]
    assert "当前作品或后代作品" in reference_tool["description"]
    assert "高度压缩或反用" in reference_tool["description"]
    assert "不要先用本工具重复试探" in reference_tool["description"]

    text_param = reference_tool["parameters"]["properties"]["text"]
    assert "目标短句" in text_param["description"]

    retrieval_tool = agent.TEXT_RETRIEVAL_TOOL["function"]
    assert retrieval_tool["name"] == "search_predecessor_texts"
    assert "自建古典诗词 Corpus" in retrieval_tool["description"]
    assert "借了谁哪一句诗" in retrieval_tool["description"]
    assert "长尾互文" in retrieval_tool["description"]


def test_reference_tool_queries_target_clause_and_returns_candidates(
    monkeypatch,
    agent,
):
    create_calls = []
    search_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        if len(create_calls) == 1:
            return _tool_call_response(
                "ref-1",
                "lookup_reference",
                json.dumps(
                    {"text": "片片轻鸥落晚沙"},
                    ensure_ascii=False,
                ),
            )
        return _text_response("这句与杜甫《小寒食舟中作》关系最直接。")

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
                type="reference",
                text="片片輕鷗下急湍",
                source={
                    "title": "小寒食舟中作",
                    "author": "杜甫",
                    "work": "小寒食舟中作",
                },
                provider="cnkgraph",
                status="candidate",
                metadata={"dynasty": "唐"},
            )
        ]

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(agent.evidence_service, "search", fake_search)

    result = agent.graph.invoke(
        {
            "poem": "片片轻鸥落晚沙。",
            "question": "这句改用了谁的诗？",
            "selection": None,
        }
    )

    assert search_calls == [
        {
            "query": "片片轻鸥落晚沙",
            "provider_name": "cnkgraph",
            "evidence_type": "reference",
        }
    ]
    assert result["reply"] == "这句与杜甫《小寒食舟中作》关系最直接。"
    assert result["tool_count"] == 1
    assert result["evidences"][0]["metadata"]["dynasty"] == "唐"




def test_local_retrieval_tool_is_hidden_when_service_is_disabled(
    monkeypatch,
    agent,
):
    monkeypatch.setattr(
        agent,
        "text_retrieval_client",
        SimpleNamespace(enabled=False),
    )

    names = [
        item["function"]["name"]
        for item in agent._available_tools()
    ]

    assert "search_predecessor_texts" not in names


def test_local_retrieval_tool_adds_host_poem_context_and_returns_candidates(
    monkeypatch,
    agent,
):
    create_calls = []
    retrieval_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        if len(create_calls) == 1:
            return _tool_call_response(
                "retrieval-1",
                "search_predecessor_texts",
                json.dumps(
                    {"text": "片片轻鸥落晚沙"},
                    ensure_ascii=False,
                ),
            )
        return _text_response("最值得比较的是杜甫《小寒食舟中作》。")

    class FakeRetrievalClient:
        enabled = True

        async def search(self, *, text, current_poem, top_k):
            retrieval_calls.append(
                {
                    "text": text,
                    "current_poem": current_poem,
                    "top_k": top_k,
                }
            )
            return RetrievalSearchResponse(
                status="ok",
                query=text,
                candidates=[
                    RetrievalCandidate(
                        rank=1,
                        work_id="dufu-1",
                        title="小寒食舟中作",
                        author="杜甫",
                        dynasty="唐",
                        text="片片轻鸥下急湍。",
                        chronology_status="clearly_earlier",
                        support_count=2,
                    )
                ],
            )

    monkeypatch.setattr(agent, "client", _fake_client(fake_create))
    monkeypatch.setattr(
        agent,
        "text_retrieval_client",
        FakeRetrievalClient(),
    )

    result = agent.graph.invoke(
        {
            "poem": "片片轻鸥落晚沙。",
            "question": "这句改用了谁的诗？",
            "selection": "片片轻鸥落晚沙",
            "context": agent.PoemContext(
                id="poem-1",
                title="鹧鸪天",
                author="陆游",
                dynasty="宋",
            ),
        }
    )

    assert result["reply"] == "最值得比较的是杜甫《小寒食舟中作》。"
    assert result["tool_count"] == 1
    assert result.get("evidences") == []

    assert len(retrieval_calls) == 1
    call = retrieval_calls[0]
    assert call["text"] == "片片轻鸥落晚沙"
    assert call["top_k"] == 8
    assert call["current_poem"].text == "片片轻鸥落晚沙。"
    assert call["current_poem"].author == "陆游"
    assert call["current_poem"].dynasty == "宋"

    tool_names = {
        item["function"]["name"]
        for item in create_calls[0]["tools"]
    }
    assert "search_predecessor_texts" in tool_names

    tool_message = next(
        message
        for message in create_calls[1]["messages"]
        if message.get("role") == "tool"
    )
    payload = json.loads(tool_message["content"])
    assert payload["evidence_type"] == "text_retrieval"
    assert payload["candidates"][0]["author"] == "杜甫"
    assert payload["candidates"][0]["text"] == "片片轻鸥下急湍。"


def test_agent_prompt_prioritizes_corpus_retrieval_for_textual_provenance(agent):
    prompt = agent.compose_prompt("agent_decide")

    assert "应优先使用它" in prompt
    assert "即使目标短语同时带有典故色彩" in prompt
    assert "不要仅因为首轮 miss 就改用典故工具" in prompt
    assert "不要先用 `lookup_reference`" in prompt
