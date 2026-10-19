"""Document RAG 首轮 BM25 只读实验的确定性回归。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.retrieval.document.lexical import tokenize
from scripts.experiments.document_rag_lexical_baseline import (
    SectionBM25,
    checked_cases,
    checked_sections,
    grade_case,
    run,
    section_key,
)


def fixture_section(name: str, file_name: str, identifier: str, text: str) -> dict[str, str]:
    return {
        "doc": name, "file": file_name, "section_id": identifier,
        "title": "示例条目", "text": text,
    }


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_section_keys_include_source_file() -> None:
    first = fixture_section("词话", "卷一.xhtml", "1", "飞卿评词")
    second = fixture_section("词话", "卷二.xhtml", "1", "姜夔评词")
    assert section_key(first) != section_key(second)


def test_unicode_normalization_but_no_implicit_alias_expansion() -> None:
    assert tokenize("ＡＢＣ 古典") == ["abc", "古典"]
    assert "陳廷焯" not in tokenize("陈廷焯")


def test_search_does_not_use_gold_answer() -> None:
    sections = [
        fixture_section("书甲", "a.xhtml", "1", "飞卿章法颠倒"),
        fixture_section("书乙", "b.xhtml", "1", "姜夔清空骚雅"),
    ]
    searcher = SectionBM25(sections)
    assert searcher.search("姜夔清空", 1)[0][0] == section_key(sections[1])
    assert searcher.search("无共同词项", 1) == []


def test_multisection_gold_requires_all_targets() -> None:
    case = {
        "id": "x", "question": "不同文献怎么评价姜夔？",
        "gold_evidence": [
            {"document": "书甲", "epub_xhtml": "a.xhtml", "epub_section_id": "1"},
            {"document": "书乙", "epub_xhtml": "b.xhtml", "epub_section_id": "1"},
        ],
    }
    score = grade_case(case, [("书甲|a.xhtml|1", 8.0)], 5)
    assert score["hit_at_k"] is True
    assert score["all_gold_at_k"] is False
    assert score["recall_at_k"] == 0.5
    assert score["reciprocal_rank"] == 1.0


def test_invalid_quote_is_rejected(tmp_path: Path) -> None:
    sections = [fixture_section("书甲", "a.xhtml", "1", "真实原文")]
    case = {
        "id": "x", "split": "development", "gold_status": "gold_checked",
        "gold_evidence": [{
            "document": "书甲", "epub_xhtml": "a.xhtml",
            "epub_section_id": "1", "quote": "不存在的原文",
        }],
    }
    cases = write_json(tmp_path / "cases.json", {"status": "draft", "cases": [case]})
    with pytest.raises(ValueError, match="Gold 引文未出现"):
        checked_cases(cases, sections)


def test_duplicate_section_key_is_rejected(tmp_path: Path) -> None:
    entry = fixture_section("书甲", "a.xhtml", "1", "正文")
    corpus = write_json(tmp_path / "corpus.json", [entry, entry])
    with pytest.raises(ValueError, match="重复来源定位键"):
        checked_sections(corpus)


def test_runner_excludes_holdout_and_records_input_fingerprints(tmp_path: Path) -> None:
    sections = [
        fixture_section("书甲", "a.xhtml", "1", "飞卿章法颠倒"),
        fixture_section("书乙", "b.xhtml", "2", "姜夔清空骚雅"),
    ]

    def case(id: str, split: str) -> dict:
        return {
            "id": id, "question": "姜夔清空",
            "split": split, "gold_status": "gold_checked", "local_coverage": "in_corpus",
            "gold_evidence": [{
                "document": "书乙", "epub_xhtml": "b.xhtml",
                "epub_section_id": "2", "quote": "姜夔清空",
            }],
        }
    corpus = write_json(tmp_path / "corpus.json", sections)
    cases = write_json(tmp_path / "cases.json", {
        "status": "draft", "cases": [case("dev", "development"), case("holdout", "holdout")]
    })
    report = tmp_path / "output/result.json"
    result = run(corpus, cases, report)
    assert result["summary"]["cases"] == 1
    assert result["summary"]["hit_at_k"] == 1.0
    assert result["results"][0]["case_id"] == "dev"
    assert result["inputs"]["corpus_sha256"]
    assert result["inputs"]["cases_sha256"]
    assert json.loads(report.read_text())["scope"] == "development_in_corpus_only"
