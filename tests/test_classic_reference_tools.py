"""Structured dictionary/Wikisource and scoped web source tests."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.ai.tools import available_tools
from backend.research.classic_references import (
    ClassicReferencesClient, ReferenceSourceError,
)
from backend.research.deepseek_web import DeepSeekWebClient


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def create(*args, **kwargs):
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", create)
    return ClassicReferencesClient()


def js(data, status=200):
    return httpx.Response(status, json=data, headers={"content-type": "application/json"})


def test_registration_defaults_off():
    names = [t["function"]["name"] for t in available_tools(False)]
    assert not {"lookup_moedict", "search_wikisource", "read_wikisource_page"} & set(names)
    enabled = [t["function"]["name"] for t in available_tools(False, False, False, False, True)]
    assert enabled[-3:] == ["lookup_moedict", "search_wikisource", "read_wikisource_page"]


def test_moedict_official_api_preserves_original_and_citation(monkeypatch):
    def handler(request):
        assert request.url.host == "www.moedict.tw"
        assert request.url.path == "/a/將息.json"
        return js({"t":"將息","h":[{"b":"ㄐㄧㄤ ㄒㄧˊ","p":"jiāng xí","d":[{
            "f":"\u0060調養~\u0060休息~。",
            "q":["\u0060宋~\u0060李清照~〈聲聲慢〉：乍暖還寒。"],
        }]}]})
    client = mock_client(monkeypatch, handler)
    result = asyncio.run(client.lookup_moedict("將息"))
    assert result["status"] == "ok"
    assert result["entries"][0]["definitions"][0]["definition_original"] == "\u0060調養~\u0060休息~。"
    assert "《重编国语辞典修订本》" in result["license_note"]
    assert "CC BY-ND" in result["license_note"]
    assert result["url"].endswith("/a/%E5%B0%87%E6%81%AF")


def test_moedict_no_hit_and_invalid_term(monkeypatch):
    client = mock_client(monkeypatch, lambda _: js({"error":"nothing"},status=404))
    assert asyncio.run(client.lookup_moedict("不存在"))["status"] == "no_hit"
    with pytest.raises(ValueError):
        asyncio.run(client.lookup_moedict("甲"*17))


def test_wikisource_search_provides_page_ids_and_strips_html(monkeypatch):
    def handler(req):
        assert req.url.host == "zh.wikisource.org"
        assert req.url.params["action"] == "query"
        assert req.url.params["srnamespace"] == "0"
        return js({"query":{"search":[
            {"pageid":7216,"title":"人間詞話","snippet":"<span class=\"searchmatch\">境界</span>為最上"},
            {"pageid":1214281,"title":"人間詞話 (1926)","snippet":"已刊"},
        ]}})
    client = mock_client(monkeypatch, handler)
    data = asyncio.run(client.search_wikisource("人間詞話"))
    assert data["status"] == "ok"
    assert [i["pageid"] for i in data["results"]] == [7216,1214281]
    assert data["results"][0]["snippet"] == "境界為最上"
    assert "wikisource.org/wiki/" in data["results"][0]["url"]


def test_wikisource_read_returns_exact_revision_and_excerpt(monkeypatch):
    def handler(req):
        assert req.url.params["pageids"] == "7216"
        assert req.url.params["rvslots"] == "main"
        return js({"query":{"pages":[{"pageid":7216,"title":"人間詞話","revisions":[{
            "revid":2222,"timestamp":"2026-10-01T00:00:00Z",
            "slots":{"main":{"content":"詞以境界為最上，" + "甲"*4000}},
        }]}]}})
    client = mock_client(monkeypatch, handler)
    d = asyncio.run(client.read_wikisource(7216))
    assert d["status"] == "ok"
    assert d["revision_id"] == 2222
    assert d["url"].endswith("oldid=2222")
    assert d["truncated"] is True
    assert len(d["wikitext_excerpt"]) == 3500


def test_wikisource_invalid_and_http_error(monkeypatch):
    client = mock_client(monkeypatch, lambda _: js({"error":{"code":"ratelimited"}},status=200))
    with pytest.raises(ReferenceSourceError, match="ratelimited"):
        asyncio.run(client.search_wikisource("詞源"))
    with pytest.raises(ValueError):
        asyncio.run(client.read_wikisource(-1))


@pytest.mark.parametrize("source,domain",[
    ("zdic","zdic.net"),("shidian","shidianguji.com"),
    ("ctext","ctext.org"),("souyun","sou-yun.cn"),
    ("wikimedia","wikisource.org"),
])
def test_scoped_search_is_domain_filtered(monkeypatch,source,domain):
    original = httpx.AsyncClient
    def handler(req):
        body=json.loads(req.content)
        assert body["query"].endswith("site:"+domain)
        return js({"results":[
            {"title":"valid","url":"https://www."+domain+"/entry","snippet":"a"},
            {"title":"other","url":"https://irrelevant.net","snippet":"b"},
        ]})
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args,**kwargs:
                        original(*args,transport=transport,**kwargs))
    monkeypatch.setenv("DEEPSEEK_WEB_API_KEY","placeholder")
    c=DeepSeekWebClient()
    r=asyncio.run(c.search("李清照 词论",source=source))
    assert r["source"] == source
    assert [x["title"] for x in r["results"]]==["valid"]


def test_agent_requires_prior_wikisource_search(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY","dummy")
    from backend.ai import graph as ag
    monkeypatch.setattr(ag,"CLASSIC_REFERENCE_TOOLS_ENABLED",True)
    async def forbid(pageid):
        raise AssertionError("Unsearched page cannot be read")
    monkeypatch.setattr(ag.classic_references_client,"read_wikisource",forbid)
    state={"poem":"","question":"原文","messages":[],
           "tool_calls":[{"id":"w0","name":"read_wikisource_page",
                          "arguments":'{"pageid":7216}'}]}
    out=ag.execute_tools(state)
    assert json.loads(out["tool_results"][0]["content"])["status"] == "error"
    assert "本轮" in json.loads(out["tool_results"][0]["content"])["message"]


def test_agent_search_and_read_same_request(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY","dummy")
    from backend.ai import graph as ag
    monkeypatch.setattr(ag,"CLASSIC_REFERENCE_TOOLS_ENABLED",True)
    async def search(q):
        return {"provider":"wikisource","status":"ok","results":[{"pageid":7216,"title":"人間詞話"}]}
    async def read(pageid):
        assert pageid == 7216
        return {"provider":"wikisource","status":"ok","revision_id":2222,"wikitext_excerpt":"境界"}
    monkeypatch.setattr(ag.classic_references_client,"search_wikisource",search)
    monkeypatch.setattr(ag.classic_references_client,"read_wikisource",read)
    out=ag.execute_tools({"poem":"","question":"查词话","messages":[],"tool_calls":[
        {"id":"one","name":"search_wikisource","arguments":'{"query":"人間詞話"}'},
        {"id":"two","name":"read_wikisource_page","arguments":'{"pageid":7216}'},
    ]})
    assert out["tool_count"] == 2
    assert [json.loads(x["content"])["status"] for x in out["tool_results"]] == ["ok","ok"]


def test_agent_source_search_routing(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY","dummy")
    from backend.ai import graph as ag
    monkeypatch.setattr(ag,"DEEPSEEK_WEB_TOOLS_ENABLED",True)
    async def search(query,source="all"):
        assert source=="zdic"
        return {"status":"no_hit","provider":"deepseek_web","results":[]}
    monkeypatch.setattr(ag.deepseek_web_client,"search",search)
    out=ag.execute_tools({"poem":"","question":"字义","messages":[],"tool_calls":[
        {"id":"z","name":"web_search","arguments":'{"query":"綢繆","source":"zdic"}'},
    ]})
    assert json.loads(out["tool_results"][0]["content"])["status"]=="no_hit"
