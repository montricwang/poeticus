"""DeepSeek web research adapters and ReAct tool-safety regression tests."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.ai.tools import available_tools
from backend.research.deepseek_web import (
    DeepSeekWebClient, DeepSeekWebError, _safe_public_url,
)


def make_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def create(*args, **kwargs):
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", create)
    monkeypatch.setenv("DEEPSEEK_WEB_API_KEY", "sample-fake-key")
    return DeepSeekWebClient()


def json_response(data, code=200):
    return httpx.Response(code, headers={"content-type": "application/json"}, json=data)


def result_item(url="https://example.org/source"):
    return {
        "url": url, "title": "《词论》",
        "site_name": "Example",
        "date": "2026-10-19T12:00:00+00:00",
        "snippet": "宋代词论材料", "summary": "权威原文有待核对",
        "authority": 3, "rerank_score": 1.9,
    }


def test_registry_is_explicit_and_independent_of_cnkgraph():
    basic = [t["function"]["name"] for t in available_tools(False)]
    assert "web_search" not in basic
    assert "web_fetch" not in basic
    enabled = [t["function"]["name"] for t in available_tools(False, False, False, True)]
    assert enabled[-2:] == ["web_search", "web_fetch"]


def test_search_calls_official_endpoint_without_page_content(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        assert request.headers["authorization"] == "Bearer sample-fake-key"
        return json_response({"results": [
            result_item(), result_item("https://127.0.0.1/private"),
            result_item(), result_item("http://example.net/article"),
        ]})

    c = make_client(monkeypatch, handler)
    response = asyncio.run(c.search("李清照 词别是一家 原文"))
    assert calls == [(
        "/v1/tools/search",
        {"query": "李清照 词别是一家 原文", "count": 5, "need_content": False},
    )]
    assert response["status"] == "ok"
    assert len(response["results"]) == 2
    assert response["results"][0]["url"] == "https://example.org/source"
    assert "content" not in response["results"][0]
    assert response["results"][0]["authority"] == 3


def test_search_no_results_is_no_hit(monkeypatch):
    c = make_client(monkeypatch, lambda _: json_response({"results": []}))
    response = asyncio.run(c.search("不存在的词"))
    assert response["status"] == "no_hit"
    assert response["results"] == []


@pytest.mark.parametrize("raw", [
    "file:///etc/passwd", "http://localhost/admin",
    "https://127.0.0.1/status", "http://[::1]/",
    "https://192.168.1.1/", "http://example.com:8080/",
    "http://foo.internal/status", "https://user:pass@example.org/",
    "https://example.org/\r\nX-a:bad", "https://example.org/a b",
    "http://example.org@localhost/private", "https://nohost",
])
def test_reject_local_and_nonpublic_urls(raw):
    assert _safe_public_url(raw) is None


def test_fetch_rejects_non_search_url_without_request(monkeypatch):
    def fail_handler(_):
        raise AssertionError("Must not send a network request")

    c = make_client(monkeypatch, fail_handler)
    with pytest.raises(ValueError, match="本轮搜索"):
        asyncio.run(c.fetch("https://attacker.org/other", {"https://example.org/source"}))
    with pytest.raises(ValueError):
        asyncio.run(c.fetch("http://127.0.0.1/secrets", {"http://127.0.0.1/secrets"}))


def test_fetch_provides_bounded_markdown_from_whitelisted_url(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.url.path, json.loads(request.content)))
        return json_response({
            "title": "白雨斋词话", "content": "引用原文。\\n" + "甲" * 9000
        })

    c = make_client(monkeypatch, handler)
    response = asyncio.run(c.fetch("https://example.org/source", {"https://example.org/source"}))
    assert seen == [("/v1/tools/fetch", {"url": "https://example.org/source"})]
    assert response["url"] == "https://example.org/source"
    assert response["truncated"] is True
    assert len(response["content_excerpt"]) == 3500
    assert "未经验证" in response["note"]


@pytest.mark.parametrize("code", [400, 401, 402, 403, 404, 429, 500])
def test_http_errors_are_distinct_from_no_hit(monkeypatch, code):
    c = make_client(monkeypatch, lambda _: json_response({"error": "no"}, code))
    with pytest.raises(DeepSeekWebError, match=f"HTTP {code}"):
        asyncio.run(c.search("李清照"))


def test_oversize_and_invalid_json_are_errors(monkeypatch):
    orig = httpx.AsyncClient
    c = make_client(monkeypatch, lambda _: httpx.Response(
        200, headers={"content-type": "application/json"}, content=b"x" * (192 * 1024 + 1)
    ))
    with pytest.raises(DeepSeekWebError, match="响应过大"):
        asyncio.run(c.search("苏轼"))
    monkeypatch.setattr(httpx, "AsyncClient", orig)
    c = make_client(monkeypatch, lambda _: httpx.Response(
        200, headers={"content-type": "application/json"}, content=b"{"
    ))
    with pytest.raises(DeepSeekWebError, match="无效 JSON"):
        asyncio.run(c.search("苏轼"))


def test_agent_dispatch_search_then_fetch_with_result_whitelist(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent
    monkeypatch.setattr(agent, "DEEPSEEK_WEB_TOOLS_ENABLED", True)
    monkeypatch.setattr(agent, "CNKGRAPH_RESEARCH_TOOLS_ENABLED", False)
    actions = []

    async def fake_search(q):
        actions.append(("search", q))
        return {
            "status": "ok", "provider": "deepseek_web", "query": q,
            "results": [{"title": "词论", "url": "https://example.org/source"}],
        }

    async def fake_fetch(url, allowed):
        actions.append(("fetch", url, sorted(allowed)))
        return {"status": "ok", "provider": "deepseek_web", "url": url, "content_excerpt": "词别是一家"}

    monkeypatch.setattr(agent.deepseek_web_client, "search", fake_search)
    monkeypatch.setattr(agent.deepseek_web_client, "fetch", fake_fetch)

    state = {
        "poem": "", "question": "原文是什么？", "messages": [],
        "tool_calls": [
            {"id": "search-call", "name": "web_search", "arguments": '{"query":"李清照 词论"}'},
            {"id": "fetch-call", "name": "web_fetch", "arguments": '{"url":"https://example.org/source"}'},
        ],
    }
    output = agent.execute_tools(state)
    assert actions == [
        ("search", "李清照 词论"),
        ("fetch", "https://example.org/source", ["https://example.org/source"]),
    ]
    assert output["tool_count"] == 2
    assert [json.loads(x["content"])["status"] for x in output["tool_results"]] == ["ok", "ok"]

    # Valid across sequential rounds within the same Agent State as well.
    state["tool_calls"] = [{"id": "fetch-again", "name": "web_fetch",
                            "arguments": '{"url":"https://example.org/source"}'}]
    state["tool_results"] = output["tool_results"]
    state["tool_count"] = 1
    output2 = agent.execute_tools(state)
    assert json.loads(output2["tool_results"][-1]["content"])["status"] == "ok"


def test_agent_fetch_without_search_is_error_not_network(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent
    monkeypatch.setattr(agent, "DEEPSEEK_WEB_TOOLS_ENABLED", True)
    async def must_not_fetch(*args):
        raise AssertionError("Untrusted URL must not be fetched")
    monkeypatch.setattr(agent.deepseek_web_client, "fetch", must_not_fetch)
    result = agent.execute_tools({
        "poem": "", "question": "获取页面", "messages": [],
        "tool_calls": [{"id": "missing", "name": "web_fetch",
                        "arguments": '{"url":"https://example.org/source"}'}],
    })
    assert "本轮搜索" in json.loads(result["tool_results"][0]["content"])["message"]


def test_web_tools_off_are_hidden_and_rejected_at_execution(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent
    monkeypatch.setattr(agent, "DEEPSEEK_WEB_TOOLS_ENABLED", False)
    with pytest.raises(ValueError, match="未开放"):
        agent._validate_registered_tool({
            "id": "search", "name": "web_search", "arguments": '{"query":"词论"}',
        })


def test_search_accepts_only_schema_valid_query(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from backend.ai import graph as agent
    monkeypatch.setattr(agent, "DEEPSEEK_WEB_TOOLS_ENABLED", True)
    for value in [True, 12, "", "  ", "语" * 129]:
        with pytest.raises(ValueError):
            agent._parse_tool_query({
                "id": "x", "name": "web_search", "arguments": json.dumps({"query": value})
            })
