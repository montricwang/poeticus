"""Document Tool 与现有 LangGraph Agent 的契约和回归。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.evidence.schema import EvidenceItem, EvidenceSource
from backend.retrieval.document.service import DocumentSearchResult, DocumentRetrieval, DocumentRetrievalError
from backend.ai.tools import available_tools, DOCUMENT_RETRIEVAL_TOOL


def fake_client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def tool_call(name, args):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(
            id="doc-1", type="function",
            function=SimpleNamespace(name=name, arguments=json.dumps(args, ensure_ascii=False)),
        )],
    ))])


def final(text):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=text, tool_calls=None),
    )])


def sample_evidence() -> EvidenceItem:
    return EvidenceItem(
        anchor="白石氣體超妙",
        type="commentary",
        text="美成、白石，各有至處，不必過為軒輊。",
        provider="document_corpus",
        status="candidate",
        source=EvidenceSource(title="白石氣體超妙", work="白雨齋詞話", author="陳廷焯"),
        metadata={
            "source_key": "白雨齋詞話|c3_bai_yu_zhai_ci_hua_2.xhtml|4",
            "volume": "卷二",
            "source_locator": {"epub_file": "c3_bai_yu_zhai_ci_hua_2.xhtml",
                               "heading_id": "bai_shi_qi_ti_chao_miao"},
        },
    )


def test_tool_registration_respects_local_capability() -> None:
    names_disabled = [tool["function"]["name"] for tool in available_tools(False)]
    names_enabled = [tool["function"]["name"] for tool in available_tools(False, True)]
    assert names_disabled == ["lookup_allusion", "lookup_reference"]
    assert names_enabled == [*names_disabled, "search_documents"]
    parameters = DOCUMENT_RETRIEVAL_TOOL["function"].get("parameters")
    assert isinstance(parameters, dict) and parameters["required"] == ["queries"]


def test_agent_uses_document_tool_and_returns_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.ai import graph as agent

    calls = []
    question = "陈廷焯如何比较周邦彦与姜夔？"
    seen = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            assert "search_documents" in [t["function"]["name"] for t in kwargs["tools"]]
            return tool_call("search_documents", {"queries": [
                "陈廷焯 美成 白石 顿挫 理法", "白雨斋词话 清真 白石 气体超妙",
            ]})
        return final("陈廷焯认为美成擅顿挫理法，白石以气体超妙见长（《白雨斋词话》卷二）。")

    def search(input_question, *, extra_queries):
        seen.append((input_question, extra_queries))
        return DocumentSearchResult(
            queries=[input_question, *extra_queries],
            evidences=[sample_evidence()],
        )

    monkeypatch.setattr(agent, "client", fake_client(create))
    monkeypatch.setattr(DocumentRetrieval, "enabled", property(lambda self: True))
    monkeypatch.setattr(agent.document_retrieval, "search", search)
    result = agent.graph.invoke({"poem": "", "question": question})

    assert seen == [(question, (
        "陈廷焯 美成 白石 顿挫 理法", "白雨斋词话 清真 白石 气体超妙"
    ))]
    assert len(calls) == 2
    payload = next(json.loads(m["content"]) for m in calls[1]["messages"] if m.get("role") == "tool")
    assert payload["status"] == "ok"
    assert payload["evidence_type"] == "commentary"
    assert payload["evidences"][0]["source"]["work"] == "白雨齋詞話"
    assert payload["evidences"][0]["metadata"]["volume"] == "卷二"
    assert result["evidences"][0]["text"].startswith("美成、白石")
    assert result["reply"].startswith("陈廷焯认为")


@pytest.mark.parametrize("args", [
    {}, {"queries": []}, {"queries": ["  "]},
    {"queries": ["x", "y", "z"]}, {"queries": [3]},
    {"queries": ["x" * 181]},
])
def test_bad_document_queries_do_not_reach_provider(
    monkeypatch: pytest.MonkeyPatch, args: object,
) -> None:
    from backend.ai import graph as agent

    called = []
    responses = []

    def create(**kwargs):
        responses.append(kwargs)
        if len(responses) == 1:
            return tool_call("search_documents", args)
        return final("文献检索参数不合法。")

    def search(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("bad query must not reach DB")

    monkeypatch.setattr(agent, "client", fake_client(create))
    monkeypatch.setattr(agent.document_retrieval, "search", search)
    monkeypatch.setattr(DocumentRetrieval, "enabled", property(lambda self: True))
    result = agent.graph.invoke({"poem": "", "question": "查询一条词话"})
    tool_result = next(json.loads(m["content"]) for m in responses[1]["messages"] if m.get("role") == "tool")
    assert tool_result["status"] == "error"
    assert not called
    assert result["reply"] == "文献检索参数不合法。"


def test_database_failure_returns_tool_error_without_fake_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.ai import graph as agent

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return tool_call("search_documents", {"queries": ["美成 白石"]})
        return final("当前文献数据库不可用，无法核实原文。")

    def search(*_args, **_kwargs):
        raise DocumentRetrievalError("本地文献检索服务暂时不可用")

    monkeypatch.setattr(agent, "client", fake_client(create))
    monkeypatch.setattr(agent.document_retrieval, "search", search)
    monkeypatch.setattr(DocumentRetrieval, "enabled", property(lambda self: True))
    result = agent.graph.invoke({"poem": "", "question": "周邦彦与姜夔？"})
    payload = next(json.loads(m["content"]) for m in calls[1]["messages"] if m.get("role") == "tool")
    assert payload["status"] == "error"
    assert payload["evidences"] == []
    assert result.get("evidences") == []
    assert result["reply"].startswith("当前文献数据库不可用")


def test_document_service_is_off_by_default_without_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    monkeypatch.setenv("POETICUS_DOCUMENT_RAG_ENABLED", "false")
    instance = DocumentRetrieval(model_path=Path("/example/never-installed"), dsn="postgresql://example")
    assert not instance.enabled
