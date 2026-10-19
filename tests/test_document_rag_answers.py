"""四书 RAG 问答实验：查询扩展、证据来源与 LLM 调用契约。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scripts.experiments.document_rag_answers import (
    LocalHybrid,
    agentic_answer,
    analyze_citations,
    evidence_message,
    final_messages,
    read_planned_queries,
    run_case,
)


def sample_evidence() -> list[dict[str, Any]]:
    return [{
        "id": 1, "key": "白雨齋詞話|卷二.xhtml|1",
        "document": "白雨齋詞話", "volume": "卷二",
        "group": None, "title": "美成白石各有至處",
        "text": "美成、白石，各有至處，不必過為軒輊。",
        "truncated": False,
    }]


def tool_response(queries: Any) -> Any:
    call = SimpleNamespace(
        type="function", function=SimpleNamespace(
            name="search_document_corpus",
            arguments=queries,
        ),
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])


def test_query_expansion_accepts_two_and_rejects_invalid_tool_arguments() -> None:
    actual = read_planned_queries(tool_response('{"queries":["周邦彦 美成","姜夔 白石"]}'))
    assert actual == ["周邦彦 美成", "姜夔 白石"]
    with pytest.raises(ValueError, match="查询条数或长度"):
        read_planned_queries(tool_response('{"queries":[]}'))
    with pytest.raises(ValueError, match="合法 JSON"):
        read_planned_queries(tool_response("bad json"))


def test_original_question_is_always_preserved_and_queries_are_bounded() -> None:
    search = object.__new__(LocalHybrid)
    search.sections = {
        "白雨齋詞話|卷二.xhtml|1": {
            "doc": "白雨齋詞話", "file": "卷二.xhtml", "section_id": "1",
            "title": "美成白石各有至處", "volume": "卷二",
            "text": "美成、白石，各有至處，不必過為軒輊。",
        },
    }
    requested = []

    def fake_retrieve(q: str) -> list[tuple[str, float]]:
        requested.append(q)
        return [("白雨齋詞話|卷二.xhtml|1", 1.0)]

    search.retrieve = fake_retrieve  # type: ignore[method-assign]
    question = "陈廷焯如何比较周邦彦和姜夔？"
    queries, evidence = search.search(question, ["美成 白石", "姜夔 白石"])
    assert queries == [question, "美成 白石", "姜夔 白石"]
    assert requested == queries
    assert len(evidence) == 1
    assert evidence[0]["key"].endswith("|1")
    with pytest.raises(ValueError, match="最多"):
        search.search(question, ["a", "b", "c"])


def test_prompt_contains_source_but_not_gold_expected_answer() -> None:
    evidence = sample_evidence()
    plain = final_messages("问题？", None)
    augmented = final_messages("问题？", evidence)
    assert "美成、白石" not in str(plain)
    assert "美成、白石" in str(augmented)
    assert "卷二" in evidence_message(evidence)
    assert "Gold" not in str(augmented)


def test_citation_validation_does_not_claim_grounding() -> None:
    result = analyze_citations("这句话[1]有证据，另一句[4]没有。", sample_evidence())
    assert result["citation_ids"] == [1, 4]
    assert result["invalid_citation_ids"] == [4]
    assert "不自动判断" in result["note"]


def test_agentic_calls_tool_then_generates_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearch:
        def search(self, q: str, variants: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
            assert q == "美成与白石？"
            assert variants == ["周邦彦 姜夔"]
            return [q, *variants], sample_evidence()

    requests = []

    def fake_chat(_client: object, messages: object, *, tools: bool = False) -> Any:
        requests.append((messages, tools))
        return tool_response('{"queries":["周邦彦 姜夔"]}')

    def fake_answer(_client: object, question: str, evidence: object) -> str:
        assert question == "美成与白石？"
        assert evidence == sample_evidence()
        return "二者各有长处。[1]"

    monkeypatch.setattr("scripts.experiments.document_rag_answers.chat", fake_chat)
    monkeypatch.setattr("scripts.experiments.document_rag_answers.answer", fake_answer)
    result = agentic_answer(None, "美成与白石？", FakeSearch())  # type: ignore[arg-type]
    assert result[1] == ["美成与白石？", "周邦彦 姜夔"]
    assert result[0].endswith("[1]")
    assert requests[0][1] is True


def test_run_case_separates_retrieval_evidence_and_answer_review(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSearch:
        def search(self, question: str, variants: object = ()) -> tuple[list[str], list[dict[str, Any]]]:
            return [question], sample_evidence()

    def fake_answer(_client: object, question: str, evidence: object) -> str:
        return "无文献回答" if evidence is None else "有原文。[1]"

    monkeypatch.setattr("scripts.experiments.document_rag_answers.answer", fake_answer)
    case = {
        "id": "test", "question": "陈廷焯评价什么？",
        "gold_evidence": [{
            "document": "白雨齋詞話", "epub_xhtml": "卷二.xhtml", "epub_section_id": "1",
        }],
    }
    result = run_case(case, None, FakeSearch(), ["llm_only", "hybrid"])  # type: ignore[arg-type]
    assert result["modes"]["llm_only"]["gold_hit_at_5"] is None
    assert result["modes"]["hybrid"]["gold_hit_at_5"] is True
    assert result["modes"]["hybrid"]["citations"]["invalid_citation_ids"] == []
    assert result["modes"]["hybrid"]["answer_review"] == "pending_manual_review"


def test_runner_resumes_without_repeating_api_calls(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from pathlib import Path
    from scripts.experiments import document_rag_answers as runner

    corpus = Path(tmp_path) / "corpus.json"
    cases = Path(tmp_path) / "cases.json"
    output = Path(tmp_path) / "answers.json"
    corpus.write_text("[]", encoding="utf-8")
    cases.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "load_development", lambda _c, _k: ([], [{"id": "sample", "question": "问？"}]))
    monkeypatch.setattr(runner, "LocalHybrid", lambda *_a, **_kw: object())
    monkeypatch.setattr(runner, "OpenAI", lambda **_kw: object())
    monkeypatch.setenv("LLM_API_KEY", "unit-test-key")
    calls: list[str] = []

    def run_one(case: dict[str, str], _client: object, _search: object, _modes: object) -> dict[str, str]:
        calls.append(case["id"])
        return {"id": case["id"]}

    monkeypatch.setattr(runner, "run_case", run_one)
    monkeypatch.setattr(sys, "argv", ["runner", "--corpus", str(corpus), "--cases", str(cases), "--output", str(output)])
    runner.main()
    runner.main()
    assert calls == ["sample"]
    assert list(__import__("json").loads(output.read_text())["cases"]) == ["sample"]
    cases.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="现有报告"):
        runner.main()
