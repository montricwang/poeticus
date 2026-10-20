"""Eval runner 的 Process Trace 离线测试。"""

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
    messages = [
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
    records = _tool_trace(messages)["results"]
    assert records[0]["hits"][0]["volume_id"] == "KR7a0006_1186"
    assert records[0]["hits"][0]["matched_text"] == "黄鹤楼"
    assert records[1]["analyses"][0]["wrong_rhymes"][0]["wrong_characters"] == ["壁"]
    assert long_text not in json.dumps(records, ensure_ascii=False)
    assert len(records[0]["hits"][0]["before"]) <= 65
