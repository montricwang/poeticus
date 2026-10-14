"""离线对照：现行融合后筛选 A vs 每榜单筛选/Work 重编号后融合 B。

只读现有 Poem Retrieval 模型与 Serving 资产，不更改线上排序。
例子：python -m scripts.retrieval.rrf_prefilter_ab --device cpu --case-ids longtail_luyou_dufu_gull
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Collection, Sequence, TypedDict

from backend.data_paths import MODELS_ROOT, RETRIEVAL_ROOT
from backend.retrieval.poem.pipeline.eligibility import (
    apply_candidate_eligibility,
    classify_work_eligibility,
)
from backend.retrieval.poem.pipeline.fanout import (
    QueryChannelResult,
    execute_query_fanout,
)
from backend.retrieval.poem.pipeline.fusion import FusedCandidate, fuse_candidates_rrf
from backend.retrieval.poem.pipeline.query_strategy import build_query_plan
from backend.retrieval.poem.serving import RetrievalServingRuntime
from backend.retrieval.poem.serving_paths import default_paths
from scripts.retrieval.benchmark_serving import (
    DEFAULT_CASES,
    DEFAULT_CASE_IDS,
    BenchmarkCase,
    load_cases,
)


class ABComparison(TypedDict):
    a: tuple[FusedCandidate, ...]
    b: tuple[FusedCandidate, ...]
    rankings: list[dict[str, object]]
    raw_eligible_works: int
    b_eligible_works: int
    top_k: int


def filter_and_renumber_works(
    rankings: Sequence[QueryChannelResult],
    *,
    self_work_ids: Collection[str],
    target_dynasty: str | None,
) -> tuple[list[QueryChannelResult], list[dict[str, object]]]:
    """对每张原始 Chunk 榜单筛除不合格 Work，再按首次命中重排 Work 名次。

    同榜单同 Work 只计一次，且保留首次出现的 Chunk 文本作为证据。
    不修改输入（A/B 使用完全相同的原始 Hit 对象）。
    """
    filtered: list[QueryChannelResult] = []
    diagnostics: list[dict[str, object]] = []

    for result in rankings:
        kept = []
        seen: set[str] = set()
        reasons: Counter[str] = Counter()
        rejected_head10 = 0
        first_eligible_raw_rank: int | None = None

        for hit in result.hits:
            _, reason = classify_work_eligibility(
                hit.work_id,
                hit.dynasty,
                self_work_ids=self_work_ids,
                target_dynasty=target_dynasty,
            )
            if reason is not None:
                reasons[reason] += 1
                if hit.rank <= 10:
                    rejected_head10 += 1
                continue
            if hit.work_id in seen:
                reasons["duplicate_eligible_chunk"] += 1
                continue
            seen.add(hit.work_id)
            if first_eligible_raw_rank is None:
                first_eligible_raw_rank = hit.rank
            kept.append(replace(hit, rank=len(kept) + 1))

        filtered.append(
            QueryChannelResult(
                query=result.query,
                channel=result.channel,
                hits=tuple(kept),
            )
        )
        diagnostics.append(
            {
                "query": result.query.text,
                "channel": result.channel.name,
                "raw_chunks": len(result.hits),
                "self_hit_chunks": reasons["self_hit"],
                "clearly_later_chunks": reasons["clearly_later"],
                "duplicate_eligible_chunks": reasons["duplicate_eligible_chunk"],
                "eligible_works": len(kept),
                "rejected_top10_chunks": rejected_head10,
                "first_eligible_raw_rank": first_eligible_raw_rank,
            }
        )

    return filtered, diagnostics


def compare_rankings(
    rankings: Sequence[QueryChannelResult],
    *,
    self_work_ids: Collection[str],
    target_dynasty: str | None,
    rrf_k: int = 60,
    final_top_k: int = 8,
) -> ABComparison:
    """只改变资格判断与 Work 重编号的位置，保持所有其余参数相同。"""
    if final_top_k <= 0:
        raise ValueError("final_top_k 必须为正整数")
    raw = list(rankings)

    # A：原始 Chunk rank 参与 RRF，直到最终 Top-K 前才过滤。
    a = apply_candidate_eligibility(
        fuse_candidates_rrf(raw, top_k=None, rrf_k=rrf_k),
        current_work_id=None,
        current_work_ids=self_work_ids,
        target_dynasty=target_dynasty,
    )
    # B：每张榜单先筛掉无效作品、去重且重编号，再做相同 RRF。
    filtered, diagnostics = filter_and_renumber_works(
        raw,
        self_work_ids=self_work_ids,
        target_dynasty=target_dynasty,
    )
    b = apply_candidate_eligibility(
        fuse_candidates_rrf(filtered, top_k=None, rrf_k=rrf_k),
        current_work_id=None,
        current_work_ids=self_work_ids,
        target_dynasty=target_dynasty,
    )
    return {
        "a": tuple(row.candidate for row in a.eligible),
        "b": tuple(row.candidate for row in b.eligible),
        "rankings": diagnostics,
        "raw_eligible_works": len(a.eligible),
        "b_eligible_works": len(b.eligible),
        "top_k": final_top_k,
    }


def _normalized(text: str) -> str:
    """仅用于评测 Case 原文锚点匹配，不改变检索查询或原文。"""
    return "".join(char for char in text if char.isalnum())


def _target_rank(candidates: Sequence[FusedCandidate], case: BenchmarkCase) -> int | None:
    author = case["target"]["author"]
    anchor = _normalized(case["target"]["text"])
    for rank, candidate in enumerate(candidates, 1):
        if candidate.author != author:
            continue
        if any(anchor in _normalized(ev.hit.text) for ev in candidate.evidences):
            return rank
    return None


def _case_report(
    case: BenchmarkCase,
    comparison: ABComparison,
    *,
    top_k: int,
) -> dict[str, object]:
    a = comparison["a"]
    b = comparison["b"]
    a_rank = _target_rank(a, case)
    b_rank = _target_rank(b, case)

    def preview(candidates: Sequence[FusedCandidate]) -> list[dict[str, object]]:
        return [
            {
                "rank": i,
                "work_id": c.work_id,
                "author": c.author,
                "title": c.title,
                "score": round(c.rrf_score, 7),
                "support_count": c.support_count,
                "best_rank": c.best_rank,
                "text": c.evidences[0].hit.text if c.evidences else "",
            }
            for i, c in enumerate(candidates[:top_k], 1)
        ]

    return {
        "case_id": case["id"],
        "query": case["retrieval_query"],
        "target": case["target"],
        "a_target_rank": a_rank,
        "b_target_rank": b_rank,
        "a_hit_at_5": a_rank is not None and a_rank <= 5,
        "b_hit_at_5": b_rank is not None and b_rank <= 5,
        "a_hit_at_8": a_rank is not None and a_rank <= 8,
        "b_hit_at_8": b_rank is not None and b_rank <= 8,
        "a_mrr": 1 / a_rank if a_rank is not None else 0.0,
        "b_mrr": 1 / b_rank if b_rank is not None else 0.0,
        "a_top": preview(a),
        "b_top": preview(b),
        "per_list_noise": comparison["rankings"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case-ids", nargs="+", default=list(DEFAULT_CASE_IDS))
    parser.add_argument("--data-root", type=Path, default=RETRIEVAL_ROOT)
    parser.add_argument("--model-root", type=Path, default=MODELS_ROOT)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--search-k", type=int, default=100)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = load_cases(args.cases, tuple(args.case_ids))
    runtime = RetrievalServingRuntime(
        default_paths(args.data_root, args.model_root),
        device=args.device,
        search_k=args.search_k,
        rrf_k=args.rrf_k,
    )
    results = []
    for case in cases:
        context = case["input"]["context"]
        aliases = runtime.metadata.find_current_work_aliases(
            text=case["input"]["poem"],
            author=context.get("author"),
        )
        plan = build_query_plan(case["retrieval_query"])
        raw = execute_query_fanout(
            plan,
            [runtime.sentence_dense, runtime.clause_dense, runtime.lexical],
            top_k=args.search_k,
        )
        comparison = compare_rankings(
            raw,
            self_work_ids=aliases,
            target_dynasty=context.get("dynasty"),
            rrf_k=args.rrf_k,
            final_top_k=args.top_k,
        )
        report = _case_report(case, comparison, top_k=args.top_k)
        report["resolved_current_alias_count"] = len(aliases)
        results.append(report)

    report = {
        "schema_version": "1",
        "experiment": "prefilter-renumber-vs-postfusion-filter",
        "search_k_per_query_channel": args.search_k,
        "rrf_k": args.rrf_k,
        "final_top_k": args.top_k,
        "target_definition": "author + normalized target text in fused evidence",
        "cases": results,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")

    # 只在终端输出必要摘要，避免 Top100 多榜单诊断淹没会话。
    for item in results:
        noise = item["per_list_noise"]
        print(
            item["case_id"],
            f"A={item['a_target_rank']}, B={item['b_target_rank']}",
            f"raw_chunks={sum(v['raw_chunks'] for v in noise)}",
            f"self={sum(v['self_hit_chunks'] for v in noise)}",
            f"aliases={item['resolved_current_alias_count']}",
            f"later={sum(v['clearly_later_chunks'] for v in noise)}",
            f"removed_top10={sum(v['rejected_top10_chunks'] for v in noise)}",
        )
    if args.output is not None:
        print(f"report: {args.output}")


if __name__ == "__main__":
    main()
