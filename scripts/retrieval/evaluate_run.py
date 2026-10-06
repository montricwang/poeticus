"""用固定 Dataset 计算 Retrieval Run 的 Recall@K / MRR。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.retrieval import (
    RetrievalBenchmarkDataset,
    RetrievalRun,
    evaluate_retrieval,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = RetrievalBenchmarkDataset.model_validate_json(
        args.dataset.read_text(encoding="utf-8")
    )
    run = RetrievalRun.model_validate_json(
        args.run.read_text(encoding="utf-8")
    )
    metrics = evaluate_retrieval(dataset, run)
    print(
        json.dumps(
            metrics.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
