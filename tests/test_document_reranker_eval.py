"""Document RAG 离线 Reranker 对照实验的轻量行为测试。"""
from __future__ import annotations

from scripts.experiments.document_rag_rerank_eval import grade, rrf, summarize


def test_rrf_is_stable_and_does_not_use_gold() -> None:
    channels = [["A", "B", "C"], ["B", "A", "D"]]
    assert rrf(channels, 4) == ["A", "B", "C", "D"]
    assert rrf(channels, 1) == ["A"]


def test_early_and_late_cutoff_have_different_candidate_semantics() -> None:
    # 延后截断的候选池可能与原先每个 Query 的 Top5 不同，
    # 这两者应当作为不同实验臂，而不是把差异误算到 Reranker。
    channels = [["A", "B", "C"], ["B", "C", "D"]]
    assert rrf([x[:1] for x in channels], 2) == ["A", "B"]
    assert rrf(channels, 2) == ["B", "C"]


def test_grade_uses_all_gold_and_reports_first_hit() -> None:
    result = grade(["X", "A", "B", "Y", "Z"], {"A", "B"})
    assert result["hits"] == 2
    assert result["hit"] is True
    assert result["all_gold"] is True
    assert result["rr"] == 0.5
    missed = grade(["X", "A", "Y"], {"A", "B"})
    assert missed["hits"] == 1
    assert missed["recall"] == 0.5
    assert missed["all_gold"] is False


def test_summary_ignores_disabled_reranker_and_computes_metrics() -> None:
    first = grade(["A", "X"], {"A"})
    second = grade(["X", "B"], {"A"})
    records = [{"old": first}, {"old": second}]
    assert summarize(records, "old") == {
        "n": 2, "hit@5": 0.5, "all_gold@5": 0.5,
        "recall@5": 0.5, "mrr@5": 0.5,
    }


def test_no_gold_is_used_in_candidate_merge() -> None:
    # Gold 只传入 grade，rrf 的唯一输入是各召回通道返回的 rank。
    gold = {"B"}
    result = rrf([["A", "B"], ["A", "C"]], 2)
    assert result == ["A", "B"]
    assert grade(result, gold)["hits"] == 1
