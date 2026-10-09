import json
from pathlib import Path

from evals.schema import EvalDataset


SEED_DATASET = Path(__file__).resolve().parents[1] / "evals" / "seed_cases.json"


def test_seed_eval_dataset_matches_schema():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))

    dataset = EvalDataset.model_validate(payload)

    assert dataset.schema_version == "1"
    assert dataset.dataset_version == 1
    assert len(dataset.cases) == 10


def test_seed_eval_cases_keep_stable_unique_ids():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))
    dataset = EvalDataset.model_validate(payload)

    ids = [case.id for case in dataset.cases]

    assert len(ids) == len(set(ids))


def test_seed_eval_selection_is_part_of_poem_snapshot():
    payload = json.loads(SEED_DATASET.read_text(encoding="utf-8"))
    dataset = EvalDataset.model_validate(payload)

    for case in dataset.cases:
        if case.input.selection:
            assert case.input.selection in case.input.poem


def test_seed_graph_state_preserves_history_roles():
    from evals.schema import EvalHistoryMessage
    from scripts.evals.run_seed import graph_state

    dataset = EvalDataset.model_validate_json(
        SEED_DATASET.read_text(encoding="utf-8")
    )
    case = dataset.cases[0]
    case.input.history = [
        EvalHistoryMessage(role="user", content="之前的问题"),
        EvalHistoryMessage(role="assistant", content="之前的回答"),
    ]

    state = graph_state(case)

    assert state["poem"] == case.input.poem
    assert state["question"] == case.input.question
    assert state["history"] == [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]


def test_seed_tool_trace_keeps_synthetic_evidence_preview():
    from scripts.evals.run_seed import _tool_names, _tool_trace

    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "call-1",
                "function": {
                    "name": "search_predecessor_texts",
                    "arguments": '{"text": "合成句"}',
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": json.dumps({
                "status": "ok",
                "query": "合成句",
                "evidences": [{
                    "anchor": "synthetic",
                    "text": "甲" * 250,
                    "source": {"title": "合成作品"},
                }],
            }, ensure_ascii=False),
        },
    ]

    assert _tool_names(messages) == ["search_predecessor_texts"]
    trace = _tool_trace(messages)
    assert len(trace["calls"]) == 1
    assert trace["calls"][0]["name"] == "search_predecessor_texts"
    assert len(trace["results"]) == 1
    result = trace["results"][0]
    assert result["evidence_count"] == 1
    preview = result["evidences"][0]
    assert len(preview["text_preview"]) == 240
    assert preview["source"] == {"title": "合成作品"}
