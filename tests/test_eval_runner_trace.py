"""Eval runner 的 Process Trace 离线测试。"""

import json


def test_tool_trace_records_arguments_results_and_evidence_preview(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    from scripts.evals.run_seed import _tool_trace

    messages = [
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

    preview = result["evidences"][0]
    assert preview["anchor"] == "刘伶"
    assert preview["source"] == {
        "title": "世说新语",
        "author": "刘义庆",
    }
    assert len(preview["text_preview"]) == 240
