"""对任意 Retriever 的排序结果计算 Poetry Retrieval Benchmark 指标。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.retrieval import (
    evaluate_retrieval_run,
    load_corpus_jsonl,
    load_retrieval_dataset,
    load_retrieval_run,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "retrieval_cases.json"
DEFAULT_CORPUS = ROOT / "evals" / "retrieval_corpus_sample.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score precomputed rankings against the Poetry Retrieval Benchmark."
    )
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--k",
        dest="ks",
        type=int,
        action="append",
        help="Recall@K；可重复传入。默认 1, 5, 20。",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ks = tuple(args.ks) if args.ks else (1, 5, 20)

    dataset = load_retrieval_dataset(args.dataset)
    corpus = load_corpus_jsonl(args.corpus)
    run = load_retrieval_run(args.rankings)

    metrics = evaluate_retrieval_run(dataset, corpus, run, ks=ks)

    print(
        f"dataset={metrics.dataset_id} "
        f"retriever={metrics.retriever_id} "
        f"cases={metrics.case_count} "
        f"MRR={metrics.mrr:.4f}"
    )
    for k, value in metrics.mean_recall_at_k.items():
        print(f"Recall@{k}={value:.4f}")

    for case in metrics.cases:
        rank = case.first_relevant_rank if case.first_relevant_rank is not None else "MISS"
        recalls = " ".join(
            f"R@{k}={value:.2f}" for k, value in case.recall_at_k.items()
        )
        print(
            f"{case.case_id}: rank={rank} "
            f"RR={case.reciprocal_rank:.4f} {recalls}"
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"saved={args.output}")


if __name__ == "__main__":
    main()
