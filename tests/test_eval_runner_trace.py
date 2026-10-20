"""Eval runner 的 Process Trace 离线测试。"""

from typing import Any
import json


def test_tool_trace_records_arguments_results_and_evidence_preview(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from scripts.evals.run_seed import _tool_trace

    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup_allusion",
                        "arguments": json.dumps(
                            {"term": "刘伶"},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": json.dumps(
                {
                    "status": "ok",
                    "query": "刘伶",
                    "evidences": [
                        {
                            "anchor": "刘伶",
                            "provider": "cnkgraph",
                            "status": "candidate",
                            "text": "甲" * 500,
                            "source": {
                                "title": "世说新语",
                                "author": "刘义庆",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]

    trace = _tool_trace(messages)

    assert trace["calls"] == [
        {
            "id": "call-1",
            "name": "lookup_allusion",
            "arguments": {"term": "刘伶"},
        }
    ]

    result = trace["results"][0]
    assert result["tool_call_id"] == "call-1"
    assert result["status"] == "ok"
    assert result["query"] == "刘伶"
    assert result["evidence_count"] == 1

    evidences = result["evidences"]
    assert isinstance(evidences, list)
    preview = evidences[0]
    assert isinstance(preview, dict)
    assert preview["anchor"] == "刘伶"
    assert preview["source"] == {
        "title": "世说新语",
        "author": "刘义庆",
    }
    preview_text = preview["text_preview"]
    assert isinstance(preview_text, str)
    assert len(preview_text) == 240


def test_structured_tool_trace_keeps_cnkgraph_book_and_ci_provenance(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    from scripts.evals.run_seed import _tool_trace

    long_text = "不得上传的受限全文" * 500
    messages: Any = [
        {
            "role": "tool", "tool_call_id": "book-1",
            "content": json.dumps({
                "status": "ok", "provider": "cnkgraph",
                "total_matches_reported": 5853,
                "hits": [{
                    "book": "钦定古今图书集成", "book_id": "KR7a0006",
                    "volume": "卷一一八六", "volume_id": "KR7a0006_1186",
                    "matched_text": "黄鹤楼",
                    "before": long_text, "after": long_text,
                }],
            }, ensure_ascii=False),
        },
        {
            "role": "tool", "tool_call_id": "meter-1",
            "content": json.dumps({
                "status": "ok", "provider": "cnkgraph",
                "analyses": [{
                    "standard": "钦谱",
                    "tune_id": 614, "format_index": "二",
                    "format_description": "双调一百字",
                    "invalid_rhymes": [{
                        "rhyme_category": "五物六月",
                        "rhyme_chars": "物、壁、雪",
                        "wrong_characters": [{"character": "壁"}],
                    }],
                    "clause_errors": [],
                }],
            }, ensure_ascii=False),
        },
    ]
    records: Any = _tool_trace(messages)["results"]
    assert records[0]["hits"][0]["volume_id"] == "KR7a0006_1186"
    assert records[0]["hits"][0]["matched_text"] == "黄鹤楼"
    assert records[1]["analyses"][0]["wrong_rhymes"][0]["wrong_characters"] == ["壁"]
    assert long_text not in json.dumps(records, ensure_ascii=False)
    assert len(records[0]["hits"][0]["before"]) <= 65

def test_bounded_source_provenance_for_web_dictionary_and_wikisource():
    from scripts.evals.run_seed import _structured_tool_preview

    long_text = "甲" * 6000
    search: Any = _structured_tool_preview({
        "provider": "deepseek_web", "source": "ctext",
        "results": [{"title": "词源", "url": "https://ctext.org/wiki.pl?chapter=123",
                     "snippet": long_text}],
    })
    assert search["source"] == "ctext"
    assert search["results"][0]["url"].startswith("https://ctext.org/")
    assert len(search["results"][0]["snippet"]) <= 130

    page: Any = _structured_tool_preview({
        "provider": "wikisource", "pageid": 7216,
        "revision_id": 2599003,
        "url": "https://zh.wikisource.org/w/index.php?oldid=2599003",
        "wikitext_excerpt": long_text,
    })
    assert page["revision_id"] == 2599003
    assert len(page["wikitext_excerpt"]) <= 240

    dictionary: Any = _structured_tool_preview({
        "provider": "moedict", "headword": "將息",
        "url": "https://www.moedict.tw/a/%E5%B0%87%E6%81%AF",
        "entries": [{"bopomofo": "ㄐㄧㄤ ㄒㄧˊ", "definitions": [
            {"definition_original": "調養、休息。", "examples_original": [long_text]},
        ]}],
    })
    assert dictionary["headword"] == "將息"
    assert dictionary["entries"][0]["definitions"][0]["definition_original"] == "調養、休息。"
    assert len(dictionary["entries"][0]["definitions"][0]["examples_original"][0]) <= 120
    assert long_text not in str(search) + str(page) + str(dictionary)
