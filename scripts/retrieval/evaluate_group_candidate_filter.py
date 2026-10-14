"""离线验证：只在候选中同时出现时压制合集重复命中，不改变线上流水线。

运行后只写本地私有报告，不修改 Corpus / SQLite / FAISS / BM25：
  python -m scripts.retrieval.evaluate_group_candidate_filter --device cpu
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from backend.data_paths import MODELS_ROOT, RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT, RETRIEVAL_ROOT
from backend.retrieval.poem.serving import RetrievalServingRuntime, ServingCandidate
from backend.retrieval.poem.serving_paths import default_paths
from scripts.retrieval.benchmark_serving import DEFAULT_CASES, BenchmarkCase, load_cases

DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_OUTPUT = RETRIEVAL_REPORTS_ROOT / "group_candidate_filter_experiment.json"
DEFAULT_EVAL_CASE_IDS = (
    "near_quote_yanweng",
    "adapted_sushi_libai_moon",
    "compressed_hezhou_lishangyin_jinse",
    "transformed_liqingzhao_fanzhongyan",
    "adapted_jiangkui_dumu_springwind",
    "compressed_jiangkui_dumu_qinglou",
    "longtail_luyou_dufu_gull",
    "longtail_yanshu_dumu_candle",
)


@dataclass(frozen=True)
class DuplicatePair:
    kept_work_id: str
    suppressed_work_id: str
    author: str
    kept_title: str | None
    suppressed_title: str | None


@dataclass(frozen=True)
class FilterResult:
    candidates: tuple[ServingCandidate, ...]
    suppressed: tuple[DuplicatePair, ...]


def _hit_matches(left: str, right: str, *, min_chars: int = 6) -> bool:
    """两份候选的命中片段必须确有文本重合，不仅作者、标题相似。"""
    a = "".join(left.split()).strip()
    b = "".join(right.split()).strip()
    return (
        len(a) >= min_chars
        and len(b) >= min_chars
        and (a in b or b in a)
    )


def suppress_retrieved_group_duplicates(
    candidates: Sequence[ServingCandidate],
    work_texts: Mapping[str, str],
    *,
    final_top_k: int = 8,
    comparison_window: int = 8,
    min_member_chars: int = 24,
) -> FilterResult:
    """仅压制同次候选中的「完整独立诗篇被较长合集收录」重复。

    必须满足：同作者、较短完整 Work 逐字出现在较长 Work 中、
    本次实际命中片段也重合。没有双方共同召回就不猜测，也不改 RRF 得分。
    """
    if final_top_k <= 0 or comparison_window < final_top_k:
        raise ValueError("筛选窗口不可小于最终 Top-K，且 Top-K 必须为正")

    in_window = candidates[:comparison_window]
    suppressed: dict[str, DuplicatePair] = {}

    for longer in in_window:
        longer_text = work_texts.get(longer.work_id)
        if not longer.author or not longer_text:
            continue
        for shorter in in_window:
            if (
                shorter.work_id == longer.work_id
                or not shorter.author
                or shorter.author != longer.author
            ):
                continue
            short_text = work_texts.get(shorter.work_id)
            if (
                not short_text
                or len(short_text) < min_member_chars
                or len(longer_text) <= len(short_text)
                or short_text not in longer_text
                or not _hit_matches(longer.text, shorter.text)
            ):
                continue
            suppressed[longer.work_id] = DuplicatePair(
                kept_work_id=shorter.work_id,
                suppressed_work_id=longer.work_id,
                author=shorter.author,
                kept_title=shorter.title,
                suppressed_title=longer.title,
            )
            break

    # 只动候选池排序结果，不重新计算 RRF。向后补齐原有候选。
    remaining = tuple(
        item for item in candidates if item.work_id not in suppressed
    )
    return FilterResult(
        candidates=remaining[:final_top_k],
        suppressed=tuple(suppressed.values()),
    )


def load_selected_work_texts(path: Path, work_ids: set[str]) -> dict[str, str]:
    """只读一次现有 85 万条 JSONL，仅保留本轮候选 Work 正文。"""
    texts: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            work_id = record["work_id"]
            if work_id in work_ids:
                texts[work_id] = record["content"]
                if len(texts) == len(work_ids):
                    break
    missing = work_ids - texts.keys()
    if missing:
        raise ValueError(f"Corpus 找不到本次候选 Work：{sorted(missing)[:5]}")
    return texts


def _normalized(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _target_rank(candidates: Sequence[ServingCandidate], case: BenchmarkCase) -> int | None:
    author = case["target"]["author"]
    target = _normalized(case["target"]["text"])
    return next(
        (
            i for i, c in enumerate(candidates, 1)
            if c.author == author and target in _normalized(c.text)
        ),
        None,
    )


def _preview(candidates: Sequence[ServingCandidate]) -> list[dict[str, object]]:
    return [
        {
            "rank": i, "work_id": c.work_id, "author": c.author,
            "title": c.title, "text": c.text,
        }
        for i, c in enumerate(candidates, 1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--search-k", type=int, default=100)
    args = parser.parse_args()

    cases = load_cases(args.cases, DEFAULT_EVAL_CASE_IDS)
    runtime = RetrievalServingRuntime(
        default_paths(RETRIEVAL_ROOT, MODELS_ROOT),
        device=args.device, search_k=args.search_k,
    )
    raw_candidates: list[tuple[BenchmarkCase, tuple[ServingCandidate, ...]]] = []
    for case in cases:
        result = runtime.search(
            case["retrieval_query"],
            current_text=case["input"]["poem"],
            current_author=case["input"]["context"].get("author"),
            target_dynasty=case["input"]["context"].get("dynasty"),
            final_top_k=32,
        )
        raw_candidates.append((case, result.candidates))

    # 另加陆游故障案例的两句查询，并分别检查「只传节选」与「传全文」。
    actual_current_work_id = "werneror_poetry:宋_2.csv:13653"
    current_full = load_selected_work_texts(args.works, {actual_current_work_id})[
        actual_current_work_id
    ]
    probes: list[tuple[str, str, tuple[ServingCandidate, ...], int]] = []
    for query in ("片片轻鸥落晚沙", "酒如清露鲊如花"):
        for label, current_text in (("excerpt", query + "。"), ("full", current_full)):
            result = runtime.search(
                query, current_text=current_text,
                current_author="陆游", target_dynasty="宋", final_top_k=32,
            )
            probes.append((f"luyou_{query}_{label}", query, result.candidates, len(result.current_work_aliases)))

    wanted = {
        c.work_id
        for _, candidates in raw_candidates for c in candidates
    }
    wanted.update(c.work_id for _, _, candidates, _ in probes for c in candidates)
    texts = load_selected_work_texts(args.works, wanted)
    report_cases: list[dict[str, object]] = []

    def analyze(name: str, query: str, candidates: tuple[ServingCandidate, ...],
                benchmark: BenchmarkCase | None = None,
                alias_count: int | None = None) -> None:
        a = candidates[:8]
        b8 = suppress_retrieved_group_duplicates(
            candidates, texts, comparison_window=8
        )
        b32 = suppress_retrieved_group_duplicates(
            candidates, texts, comparison_window=32
        )
        item: dict[str, object] = {
            "case_id": name,
            "query": query,
            "pool_size": len(candidates),
            "baseline": _preview(a),
            "b8": _preview(b8.candidates),
            "b32": _preview(b32.candidates),
            "b8_suppressed": [asdict(v) for v in b8.suppressed],
            "b32_suppressed": [asdict(v) for v in b32.suppressed],
        }
        if alias_count is not None:
            item["resolved_current_alias_count"] = alias_count
        if benchmark is not None:
            item["target_rank"] = {
                "baseline": _target_rank(a, benchmark),
                "b8": _target_rank(b8.candidates, benchmark),
                "b32": _target_rank(b32.candidates, benchmark),
            }
        report_cases.append(item)
        print(name,
              f"removed top8={len(b8.suppressed)} top32={len(b32.suppressed)}",
              f"target={item.get('target_rank', '-')}",
              flush=True)
        if b8.suppressed:
            for v in b8.suppressed:
                print(f"  {v.author}: {v.suppressed_title} -> {v.kept_title}")

    for case, candidates in raw_candidates:
        analyze(case["id"], case["retrieval_query"], candidates, case)
    for name, query, candidates, alias_count in probes:
        analyze(name, query, candidates, alias_count=alias_count)

    result = {
        "experiment": "post-eligibility local group duplicate suppression",
        "input": "unchanged Serving Top32 candidates; baseline Top8 vs B8/B32",
        "corpus": str(args.works),
        "cases": report_cases,
        "note": "Only candidates retrieved together can be paired; full-work inclusion and shared hit are required.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
