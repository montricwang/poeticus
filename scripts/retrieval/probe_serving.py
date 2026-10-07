"""Supplement the first serving benchmark with two missing diagnostics.

The main benchmark already measured resident RAM, disk, warm latency and
concurrency. This probe only adds:

1. uncached first-request latency for genuinely new query vectors;
2. benchmark-fixture self-hit exclusion for excerpt-only current poems.

It does not replace the main serving benchmark.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.retrieval.benchmark_serving import (
    DEFAULT_CASES,
    DEFAULT_CASE_IDS,
    DEFAULT_REPORT_ROOT,
    flatten_timings,
    load_cases,
    target_visible,
)
from scripts.retrieval.run_serving import (
    DEFAULT_DATA_ROOT,
    DEFAULT_MODEL_ROOT,
    default_paths,
)
from backend.retrieval.serving import RetrievalServingRuntime


def resolve_current_work_ids(
    work_path: Path,
    cases: list[dict],
) -> dict[str, set[str]]:
    """Resolve excerpt fixtures to corpus Works outside measured latency."""
    resolved = {case["id"]: set() for case in cases}
    with work_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            work = json.loads(line)
            author = work.get("author")
            content = work.get("content", "")
            if not isinstance(content, str):
                continue
            for case in cases:
                if author != case["input"]["context"].get("author"):
                    continue
                if case["current_match_text"] in content:
                    resolved[case["id"]].add(work["work_id"])
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="补测 uncached Query 与 excerpt fixture self-hit"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
    )
    parser.add_argument("--device")
    parser.add_argument("--search-k", type=int, default=100)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--output-prefix", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case_ids = tuple(args.case_ids or DEFAULT_CASE_IDS)
    cases = load_cases(args.cases, case_ids)
    paths = default_paths(args.data_root, args.model_root)

    metadata_manifest = paths.metadata_db.with_suffix(
        ".manifest.json"
    )
    if not metadata_manifest.is_file():
        raise SystemExit(
            "缺少 metadata build manifest；请先运行 "
            "python -m scripts.retrieval.build_metadata_store"
        )
    metadata_build = json.loads(
        metadata_manifest.read_text(encoding="utf-8")
    )
    current_ids = resolve_current_work_ids(
        Path(metadata_build["work_path"]),
        cases,
    )

    runtime = RetrievalServingRuntime(
        paths,
        device=args.device,
        search_k=args.search_k,
        rrf_k=args.rrf_k,
    )

    results = []
    for case in cases:
        runtime.encoder.clear_cache()
        result = runtime.search(
            case["retrieval_query"],
            current_text=case["input"]["poem"],
            current_author=case["input"]["context"].get("author"),
            target_dynasty=case["input"]["context"].get("dynasty"),
            final_top_k=args.top_k,
            current_work_ids=current_ids[case["id"]],
        )
        results.append(
            {
                "case_id": case["id"],
                "query": case["retrieval_query"],
                "resolved_current_work_ids": sorted(
                    current_ids[case["id"]]
                ),
                "target_visible": target_visible(result, case),
                "timings": flatten_timings(result),
                "candidates": [
                    {
                        "rank": item.rank,
                        "author": item.author,
                        "title": item.title,
                        "text": item.text,
                    }
                    for item in result.candidates
                ],
            }
        )

    report = {
        "schema_version": "1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "startup_profile": runtime.startup_profile,
        "cases": results,
        "note": (
            "这是补充 probe：每条 Case 前清空 query-vector cache；"
            "current Work IDs 在计时之外按作者 + current_match_text "
            "从 Corpus 解析，只用于修正 excerpt Eval fixture 的 self-hit。"
        ),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    prefix = (
        args.output_prefix
        if args.output_prefix
        else DEFAULT_REPORT_ROOT / f"retrieval_serving_probe_{stamp}"
    )
    prefix = prefix.expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)

    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Retrieval Serving Supplement Probe",
        "",
        "| case | current IDs | target visible | total ms | Qwen encode ms | sentence ANN ms | clause ANN ms | BM25 ms |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in results:
        timing = item["timings"]
        lines.append(
            "| "
            + " | ".join(
                [
                    item["case_id"],
                    str(len(item["resolved_current_work_ids"])),
                    str(item["target_visible"]),
                    f"{timing['total_ms']:.1f}",
                    f"{timing['sentence_encode_ms']:.1f}",
                    f"{timing['sentence_ann_ms']:.1f}",
                    f"{timing['clause_ann_ms']:.1f}",
                    f"{timing['bm25_ms']:.1f}",
                ]
            )
            + " |"
        )
        lines.extend(["", f"## {item['case_id']}", ""])
        for candidate in item["candidates"]:
            lines.append(
                f"- #{candidate['rank']} "
                f"{candidate['author']}《{candidate['title']}》："
                f"{candidate['text']}"
            )
    md_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(f"JSON：{json_path}")
    print(f"Markdown：{md_path}")


if __name__ == "__main__":
    main()
