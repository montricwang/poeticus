"""CNKGraph 研究工具：离线契约、工具开关与 LangGraph 回传测试。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.ai.tools import available_tools
from backend.evidence.providers.cnkgraph_research import (
    CNKGraphResearchClient,
    CNKGraphResearchError,
)


def tool_names(**kwargs):
    return [x["function"]["name"] for x in available_tools(False, **kwargs)]


def test_research_tools_disabled_by_default():
    assert tool_names() == ["lookup_allusion", "lookup_reference"]
    assert tool_names(cnkgraph_research_enabled=True) == [
        "lookup_allusion", "lookup_reference", "analyze_ci_meter",
        "search_classical_books", "lookup_ci_tune", "lookup_rhyme", "resolve_entities",
    ]


def fake_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def build(*args, **kwargs):
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build)
    return CNKGraphResearchClient()


def response(data, status=200):
    return httpx.Response(
        status,
        headers={"content-type": "application/json"},
        json=data,
    )


def test_analyze_ci_preserves_both_standards_and_flags_rhyme(monkeypatch):
    called = []

    def handler(request):
        called.append((request.url.path, json.loads(request.content)))
        return response({
            "ErrorMessage": None,
            "QinPuValidationResult": {
                "TuneName": "醉花間", "TuneId": 90, "FormatIndex": "一",
                "FormatCount": "三", "FormatDescription": "双调四十一字",
                "InvalidRhymes": [{
                    "Category": "入声", "RhymeChars": "忆、极、春",
                    "WrongChars": [{"Character": "春", "Refers": [
                        {"Category": "十一真", "Character": "春"}
                    ]}],
                }],
                "Example": [{"ValidationError": None}],
            },
            "LongPuValidationResult": {
                "TuneName": "醉花間", "TuneId": 90,
                "InvalidRhymes": None, "Example": [],
            },
        })

    client = fake_client(monkeypatch, handler)
    result = asyncio.run(client.analyze_ci("深相忆，莫相忆。", "醉花间"))

    assert called == [(
        "/api/Tool/AnalyzeCi",
        {"Content": "深相忆，莫相忆。", "TuneName": "醉花间", "RhymeBook": "词林正韵"},
    )]
    assert len(result["analyses"]) == 2
    assert result["analyses"][0]["invalid_rhymes"][0]["wrong_characters"] == [
        {"character": "春", "actual_category": ["十一真"]}
    ]
    assert result["analyses"][1]["has_reported_rhyme_errors"] is False
    assert "宋代" in result["note"]


def test_book_search_retains_provenance_but_limits_excerpt(monkeypatch):
    def handler(request):
        assert request.url.path == "/Api/Book/Find"  # Slash + case are intentional.
        assert json.loads(request.content) == {"key": "黄鹤楼", "pageNo": 1}
        return response({
            "Count": 140,
            "Result": [{
                "Category": "维基 类书类",
                "Books": [{
                    "Book": "钦定古今图书集成", "BookId": "KR7a0006",
                    "Volumes": [{
                        "Volume": "卷一一八六", "VolumeId": "KR7a0006_1186",
                        "Pages": [{
                            "MatchedText": "黄鹤楼",
                            "PreviousText": "很长" * 300,
                            "LaterText": "后文" * 300,
                        }],
                    }],
                }],
            }],
        })

    client = fake_client(monkeypatch, handler)
    result = asyncio.run(client.search_books("黄鹤楼"))
    assert result["status"] == "ok"
    assert result["total_matches_reported"] == 140
    assert result["hits"][0]["volume_id"] == "KR7a0006_1186"
    assert len(result["hits"][0]["before"]) == 110
    assert len(result["hits"][0]["after"]) == 110


def test_book_search_empty_is_no_hit(monkeypatch):
    client = fake_client(monkeypatch, lambda _: response({"Count": 0, "Result": []}))
    result = asyncio.run(client.search_books("一个肯定不存在的词"))
    assert result["status"] == "no_hit"
    assert result["hits"] == []


@pytest.mark.parametrize("status", [400, 404, 429, 500])
def test_http_failure_is_not_a_no_hit(monkeypatch, status):
    client = fake_client(monkeypatch, lambda _: response({"error": "no"}, status=status))
    with pytest.raises(CNKGraphResearchError, match=f"HTTP {status}"):
        asyncio.run(client.search_books("黄鹤楼"))


def test_invalid_json_and_oversize_are_explicit_errors(monkeypatch):
    original = httpx.AsyncClient

    def handler_invalid(_):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"not json")

    client = fake_client(monkeypatch, handler_invalid)
    with pytest.raises(CNKGraphResearchError, match="JSON"):
        asyncio.run(client.search_books("黄鹤楼"))
    # Avoid mocking the same httpx.AsyncClient factory twice.
    monkeypatch.setattr(httpx, "AsyncClient", original)

    def handler_big(_):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"x" * 99000)

    client_big = fake_client(monkeypatch, handler_big)
    with pytest.raises(CNKGraphResearchError, match="响应过大"):
        asyncio.run(client_big.search_books("黄鹤楼"))


def test_agent_parser_and_dispatch_default_disabled_then_enabled(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    from backend.ai import graph as agent

    call = {
        "id": "call-cnkg-1", "name": "analyze_ci_meter",
        "arguments": json.dumps({"tune_name": "醉花间"}),
    }
    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", False)
    with pytest.raises(ValueError, match="未启用"):
        agent._parse_tool_query(call)

    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", True)
    parsed = agent._parse_tool_query(call)
    assert parsed.tune_name == "醉花间"
    assert parsed.text == ""
    assert parsed.evidence_type == "ci_meter"
    with pytest.raises(ValueError, match="关键词"):
        agent._parse_tool_query({
            "id": "bad", "name": "search_classical_books",
            "arguments": json.dumps({"query": "x" * 71}),
        })

    observed = []

    async def analyze_ci(content, tune_name):
        observed.append((content, tune_name))
        return {"status": "ok", "analyses": [{"standard": "钦谱"}]}

    monkeypatch.setattr(agent.cnkgraph_research_client, "analyze_ci", analyze_ci)
    result = agent.execute_tools({
        "poem": "深相忆，莫相忆。",
        "question": "押韵吗？",
        "messages": [],
        "tool_calls": [call],
    })
    assert observed == [("深相忆，莫相忆。", "醉花间")]
    assert result["tool_count"] == 1
    data = json.loads(result["tool_results"][0]["content"])
    assert data["status"] == "ok"
    assert data["analyses"][0]["standard"] == "钦谱"


def test_agent_book_search_errors_remain_errors(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent
    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", True)

    async def fail(_query):
        raise CNKGraphResearchError("CNKGraph 网络请求失败或超时")

    monkeypatch.setattr(agent.cnkgraph_research_client, "search_books", fail)
    result = agent.execute_tools({
        "poem": "大江东去",
        "question": "黄鹤楼在哪部书？",
        "messages": [],
        "tool_calls": [{
            "id": "book-call",
            "name": "search_classical_books",
            "arguments": '{"query":"黄鹤楼"}',
        }],
    })
    data = json.loads(result["tool_results"][0]["content"])
    assert data["status"] == "error"
    assert "网络请求失败" in data["message"]


def test_external_timeout_is_not_a_no_hit(monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    client = fake_client(monkeypatch, handler)
    with pytest.raises(CNKGraphResearchError, match="网络请求失败或超时"):
        asyncio.run(client.search_books("黄鹤楼"))


def test_book_response_without_current_page_hits_is_partial(monkeypatch):
    client = fake_client(monkeypatch, lambda _: response({"Count": 18, "Result": []}))
    result = asyncio.run(client.search_books("黄鹤楼"))
    assert result["status"] == "partial"
    assert result["total_matches_reported"] == 18


def test_ci_response_with_missing_validation_results_is_error(monkeypatch):
    client = fake_client(monkeypatch, lambda _: response({"ErrorMessage": None}))
    with pytest.raises(CNKGraphResearchError, match="词谱校验结果"):
        asyncio.run(client.analyze_ci("深相忆，莫相忆。", "醉花间"))


def test_ci_tune_find_by_alias_then_returns_compact_formats(monkeypatch):
    requested = []

    def handler(request):
        requested.append((request.method, request.url.path))
        if request.method == "POST":
            assert json.loads(request.content) == {"key": "醉花间"}
            return response([{"Id": 90, "Name": "醉花间", "Aliases": ["醉花閒"]}])
        return response({
            "Id": 90,
            "Name": "醉花间",
            "Aliases": ["醉花閒"],
            "Desc": "唐教坊曲名",
            "WritingCount": 44,
            "Formats": [
                {
                    "FormatIndex": 0,
                    "Desc": "双调四十一字",
                    "Definition": "○○●韵●○●叠",
                    "SampleAuthor": "毛文锡",
                    "SampleContent": "深相忆，莫相忆……",
                    "FormatHtml": "<script>must-not-leak</script>",
                }
            ],
        })

    client = fake_client(monkeypatch, handler)
    data = asyncio.run(client.lookup_ci_tune("醉花间"))
    assert data["status"] == "ok"
    assert data["id"] == 90
    assert data["format_count"] == 1
    assert data["formats"][0]["definition"] == "○○●韵●○●叠"
    assert "FormatHtml" not in json.dumps(data)
    assert requested == [("POST", "/api/ciTune/find"), ("GET", "/api/ciTune/90")]


def test_ci_tune_ambiguous_results_are_not_silently_selected(monkeypatch):
    client = fake_client(monkeypatch, lambda request: response([
        {"Id": 1, "Name": "朝天子", "Aliases": []},
        {"Id": 2, "Name": "朝天乐", "Aliases": []},
    ]))
    result = asyncio.run(client.lookup_ci_tune("朝天"))
    assert result["status"] == "candidates"
    assert len(result["candidates"]) == 2


def test_rhyme_book_categories_and_character_membership(monkeypatch):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path.endswith("/0"):
            return response({
                "Book": "词林正韵",
                "Categories": [{
                    "Group": "第一部", "Name": "平声 一东二冬 通用",
                    "Id": "0", "Tone": "平",
                    "PingShuiCategories": [{
                        "Id": "东", "Name": "一东",
                        "Chars": [{"Char": "风"}, {"Char": "中"}],
                    }],
                }],
            })
        return response({
            "Book": "词林正韵",
            "Categories": [{
                "Group": "第一部", "Name": "平声 一东二冬 通用",
                "Id": "0", "Tone": "平",
            }],
        })

    client = fake_client(monkeypatch, handler)
    summary = asyncio.run(client.lookup_rhyme("词林正韵"))
    assert summary["categories"][0]["id"] == "0"
    assert summary["categories"][0]["character_present"] is None
    detail = asyncio.run(client.lookup_rhyme("词林正韵", "0", "风"))
    assert detail["categories"][0]["character_present"] is True
    assert detail["categories"][0]["char_count"] == 2
    assert requested == ["/api/rhyme/词林正韵", "/api/rhyme/词林正韵/0"]


def test_entity_labels_keep_ids_offsets_and_small_properties(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/Tool/LabelAndResolveEntity"
        assert json.loads(request.content) == {"Epoch": "宋", "Content": "苏轼在黄州"}
        return response({
            "ContentLabels": [
                {"Type": "People", "Identity": "29937", "Value": "苏轼", "Start": 0, "Length": 2}
            ],
            "Entities": [{
                "Type": "People", "Id": "29937",
                "Properties": [
                    {"Key": "显示名", "Value": "蘇軾"},
                    {"Key": "小传", "Value": "过长的传记" * 300},
                    {"Key": "字", "Value": "子瞻"},
                ],
            }],
        })

    client = fake_client(monkeypatch, handler)
    result = asyncio.run(client.resolve_entities("苏轼在黄州"))
    assert result["status"] == "ok"
    assert result["labels"] == [
        {"type": "People", "id": "29937", "text": "苏轼", "start": 0, "length": 2}
    ]
    assert result["entities"][0]["properties"] == [
        {"name": "显示名", "value": "蘇軾"}, {"name": "字", "value": "子瞻"}
    ]
    assert "过长的传记" not in json.dumps(result, ensure_ascii=False)


def test_first_batch_registered_and_dispatched_through_existing_agent(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent

    enabled = tool_names(cnkgraph_research_enabled=True)
    assert enabled == [
        "lookup_allusion", "lookup_reference",
        "analyze_ci_meter", "search_classical_books",
        "lookup_ci_tune", "lookup_rhyme", "resolve_entities",
    ]
    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", True)

    called = []

    async def fake_tune(name):
        called.append(("tune", name))
        return {"status": "ok", "name": name}

    async def fake_rhyme(book, category_id="", character=""):
        called.append(("rhyme", book, category_id, character))
        return {"status": "ok", "categories": []}

    async def fake_entities(text, epoch="宋"):
        called.append(("entities", text, epoch))
        return {"status": "ok", "labels": []}

    monkeypatch.setattr(agent.cnkgraph_research_client, "lookup_ci_tune", fake_tune)
    monkeypatch.setattr(agent.cnkgraph_research_client, "lookup_rhyme", fake_rhyme)
    monkeypatch.setattr(agent.cnkgraph_research_client, "resolve_entities", fake_entities)

    from backend.ai.context import PoemContext
    state = {
        "poem": "大江东去",
        "selection": "苏轼在黄州",
        "context": PoemContext(id="poem-1", title="念奴娇", dynasty="北宋"),
        "question": "词牌是什么？",
        "messages": [],
        "tool_calls": [
            {"id": "a", "name": "lookup_ci_tune", "arguments": '{"tune_name":"念奴娇"}'},
            {"id": "b", "name": "lookup_rhyme", "arguments": '{"book":"词林正韵","category_id":"0","character":"风"}'},
            {"id": "c", "name": "resolve_entities", "arguments": "{}"},
        ],
    }
    # Normal AGENT_MAX_TOOL_CALLS is two: exercise all three without changing config globally.
    monkeypatch.setattr(agent, "AGENT_MAX_TOOL_CALLS", 3)
    output = agent.execute_tools(state)
    assert called == [
        ("tune", "念奴娇"),
        ("rhyme", "词林正韵", "0", "风"),
        ("entities", "苏轼在黄州", "北宋"),
    ]
    assert len(output["tool_results"]) == 3
    assert all(json.loads(result["content"])["status"] == "ok"
               for result in output["tool_results"])


def test_first_batch_tools_reject_unsafe_parameters_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent

    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", False)
    for tool_name in ("lookup_ci_tune", "lookup_rhyme", "resolve_entities"):
        with pytest.raises(ValueError, match="未启用"):
            agent._parse_tool_query({
                "id": "1", "name": tool_name, "arguments": "{}",
            })

    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", True)
    for name, payload in [
        ("lookup_ci_tune", {"tune_name": 99}),
        ("lookup_rhyme", {"book": "evil", "category_id": "1"}),
        ("lookup_rhyme", {"book": "平水韵", "category_id": "x" * 41}),
        ("resolve_entities", {"text": "x" * 451}),
    ]:
        with pytest.raises(ValueError):
            agent._parse_tool_query({
                "id": "1", "name": name,
                "arguments": json.dumps(payload),
            })
