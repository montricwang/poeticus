import json

from evals.schema import EvalHistoryMessage, EvalInput, EvalPoemContext
from scripts.evals.run_retrieval_increment import (
    RetrievalIncrementCase,
    RetrievalTarget,
    _HYBRID_ADAPTER,
    _best_rank,
    _plain_messages,
    choose_current_work_id,
    choose_current_work_ids,
    compact_tool_result,
    render_markdown,
    comparison_bucket,
    scan_work_matches,
    tool_target_support,
)


def make_case() -> RetrievalIncrementCase:
    return RetrievalIncrementCase(
        id="case_one",
        tier="long_tail_probe",
        relation="adapted_quote",
        input=EvalInput(
            poem="当前句。",
            context=EvalPoemContext(
                title="当前作",
                author="今人",
                dynasty="宋",
            ),
            selection="当前句",
            question="有没有前代来源？",
        ),
        retrieval_query="当前句",
        current_match_text="当前句",
        target=RetrievalTarget(
            author="前人",
            text="前代句",
            answer_anchors=["前代句"],
        ),
        rationale="test",
    )


def test_scan_work_matches_and_choose_exact_title(tmp_path):
    works = [
        {
            "work_id": "w-current-other",
            "title": "别本",
            "author": "今人",
            "dynasty": "宋",
            "content": "当前句。",
        },
        {
            "work_id": "w-current-exact",
            "title": "当前作",
            "author": "今人",
            "dynasty": "宋",
            "content": "当前句。",
        },
        {
            "work_id": "w-target",
            "title": "前作",
            "author": "前人",
            "dynasty": "唐",
            "content": "这里有前代句。",
        },
    ]
    path = tmp_path / "works.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in works
        )
        + "\n",
        encoding="utf-8",
    )

    case = make_case()
    matches = scan_work_matches(
        work_path=path,
        cases=[case],
    )[case.id]

    assert len(matches["current"]) == 2
    assert [item["work_id"] for item in matches["target"]] == [
        "w-target"
    ]
    assert choose_current_work_id(
        case,
        matches["current"],
    ) == "w-current-exact"
    assert choose_current_work_ids(
        case,
        matches["current"],
    ) == {"w-current-other", "w-current-exact"}


def test_comparison_bucket_is_navigation_only():
    assert comparison_bucket(
        standalone_signal=True,
        tool_signal=True,
        target_supported_by_tool=True,
        eligible_rank=3,
        agent_loop_probe=False,
    ) == "standalone_knows_tool_confirms"
    assert comparison_bucket(
        standalone_signal=True,
        tool_signal=True,
        target_supported_by_tool=False,
        eligible_rank=40,
        agent_loop_probe=False,
    ) == "standalone_already_knows"
    assert comparison_bucket(
        standalone_signal=False,
        tool_signal=True,
        target_supported_by_tool=True,
        eligible_rank=40,
        agent_loop_probe=False,
    ) == "tool_increment_candidate"
    assert comparison_bucket(
        standalone_signal=True,
        tool_signal=False,
        target_supported_by_tool=False,
        eligible_rank=None,
        agent_loop_probe=True,
    ) == "single_shot_agent_loop_candidate"
    assert comparison_bucket(
        standalone_signal=False,
        tool_signal=False,
        target_supported_by_tool=False,
        eligible_rank=15,
        agent_loop_probe=False,
    ) == "retrieval_found_model_failed"
    assert comparison_bucket(
        standalone_signal=False,
        tool_signal=False,
        target_supported_by_tool=False,
        eligible_rank=None,
        agent_loop_probe=False,
    ) == "both_gap"


def test_compact_tool_result_does_not_expose_probe_metadata():
    result = {
        "ranking": [
            {
                "rank": 1,
                "title": "前作",
                "author": "前人",
                "dynasty": "唐",
                "support_count": 2,
                "chronology_status": "clearly_earlier",
                "best_evidence": {
                    "text": "前代句。",
                    "query": "当前句",
                    "channel": "dense_faiss_sentence",
                },
            }
        ],
        "probes": [
            {"work_id": "ground-truth-only"}
        ],
    }

    compact = compact_tool_result(result)

    assert compact["status"] == "ok"
    assert compact["candidates"][0]["author"] == "前人"
    assert "probes" not in compact
    assert "ground-truth-only" not in json.dumps(
        compact,
        ensure_ascii=False,
    )


def test_tool_target_support_uses_exact_target_work_id():
    result = {
        "ranking": [
            {"work_id": "noise"},
            {"work_id": "target"},
            {"work_id": "other"},
        ]
    }

    assert tool_target_support(
        result=result,
        target_work_ids={"target"},
    ) == (True, 2)
    assert tool_target_support(
        result=result,
        target_work_ids={"missing"},
    ) == (False, None)


def test_plain_chat_messages_preserve_history_roles() -> None:
    case = make_case()
    case.input.history = [
        EvalHistoryMessage(role="user", content="之前的问题"),
        EvalHistoryMessage(role="assistant", content="之前的回答"),
    ]
    messages = _plain_messages(case)
    assert messages[:2] == [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]
    assert messages[-1]["role"] == "user"
    assert "当前句。" in str(messages[-1]["content"])


def test_best_rank_ignores_non_integer_probe_values() -> None:
    probes: list[dict[str, object]] = [
        {"eligible_rank": None},
        {"eligible_rank": "2"},
        {"eligible_rank": 12},
        {"eligible_rank": 4},
    ]
    assert _best_rank(probes, "eligible_rank") == 4
    assert _best_rank(probes, "missing_rank") is None


def test_hybrid_diagnostics_retain_extra_evidence_fields() -> None:
    """Projection must not discard provenance for later manual review."""
    raw = {
        "ranking": [{
            "rank": 1,
            "work_id": "w-1",
            "title": "测试作品",
            "author": "测试作者",
            "best_evidence": {
                "text": "前代句。",
                "channel": "dense",
                "query": "当前句",
                "rank": 1,
                "source_provenance": "synthetic",
            },
            "future_candidate_field": "keep",
        }],
        "probes": [{
            "work_id": "w-1",
            "eligible_rank": 2,
            "fused_rank": 3,
            "list_supports": [{"source": "synthetic"}],
        }],
        "candidate_pool": {"fused_works": 1},
        "channels": [],
        "query_plan": [],
        "extra_diagnostic": {"keep": True},
    }
    validated = _HYBRID_ADAPTER.validate_python(raw)
    assert dict(validated).get("extra_diagnostic") == {"keep": True}
    ranks = validated.get("ranking") or []
    assert ranks
    assert dict(ranks[0]).get("future_candidate_field") == "keep"
    evidence = ranks[0].get("best_evidence")
    assert evidence is not None
    assert dict(evidence).get("source_provenance") == "synthetic"
    probes = validated.get("probes") or []
    assert probes
    assert dict(probes[0]).get("list_supports") == [{"source": "synthetic"}]


def test_markdown_report_validates_optional_case_sections() -> None:
    """The typed report boundary must preserve the generated navigation text."""
    report = {
        "schema_version": "2",
        "dataset_id": "synthetic",
        "cases": [{
            "case_id": "synthetic_case",
            "tier": "known_control",
            "relation": "adapted_quote",
            "retrieval_query": "当前句",
            "target": {"author": "前人", "text": "前代句", "answer_anchors": ["前代句"]},
            "comparison_bucket": "tool_only_signal",
            "standalone_llm": {
                "model": "synthetic",
                "answer": "独立回答",
                "target_author_mentioned": False,
                "target_anchor_hits": [],
                "target_signal": False,
            },
            "tool_augmented_llm": {
                "model": "synthetic",
                "answer": "工具回答",
                "tool_used": True,
                "tool_query": "当前句",
                "target_author_mentioned": True,
                "target_anchor_hits": ["前代句"],
                "target_signal": True,
                "tool_result": {
                    "status": "ok",
                    "note": "synthetic",
                    "candidates": [{
                        "rank": 1, "author": "前人", "title": "前代作",
                        "text": "前代句", "dynasty": "唐", "query": "当前句",
                        "channel": "bm25", "support_count": 1,
                        "chronology_status": "clearly_earlier",
                    }],
                },
            },
            "retrieval": {
                "best_fused_rank": 1,
                "best_eligible_rank": 1,
                "target_in_top5": True,
                "target_in_top20": True,
                "candidate_pool": {"fused_works": 1},
                "channels": [],
                "query_plan": [],
                "probes": [],
                "top_candidates": [{
                    "rank": 1, "author": "前人", "title": "前代作",
                    "support_count": 1, "best_evidence": {
                        "channel": "bm25", "rank": 1, "text": "前代句",
                    },
                }],
            },
        }],
    }

    markdown = render_markdown(report)
    assert "synthetic_case" in markdown
    assert "独立回答" in markdown
    assert "工具回答" in markdown
    assert "前人《前代作》" in markdown
    assert "bm25 #1: 前代句" in markdown
    assert "tool_only_signal" in markdown
