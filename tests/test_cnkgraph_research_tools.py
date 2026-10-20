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
        "search_classical_books",
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
