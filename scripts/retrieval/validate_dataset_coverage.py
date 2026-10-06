"""检查 Retrieval Benchmark 的 Ground Truth 是否真实存在于当前 Corpus。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.retrieval import (
    RetrievalBenchmarkDataset,
    benchmark_corpus_coverage,
)
from retrieval.schema import CorpusChunk


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "retrieval_cases.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that every Retrieval Benchmark target exists in the "
            "selected corpus chunks before running a retriever."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--chunks",
        type=Path,
        action="append",
        required=True,
        help="CorpusChunk JSONL；可重复传入以组合多个 corpus shard。",
    )
    return parser.parse_args()


def load_chunks(paths: list[Path]) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    seen_ids: set[str] = set()

    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    chunk = CorpusChunk.model_validate_json(line)
                except Exception as exc:
                    raise ValueError(
                        f"{path}:{line_no} CorpusChunk 无效: {exc}"
                    ) from exc

                if chunk.chunk_id in seen_ids:
                    raise ValueError(f"CorpusChunk id 重复: {chunk.chunk_id}")
                seen_ids.add(chunk.chunk_id)
                chunks.append(chunk)

    if not chunks:
        raise ValueError("Corpus chunks 不能为空")
    return chunks


def main() -> None:
    args = parse_args()
    dataset = RetrievalBenchmarkDataset.model_validate_json(
        args.dataset.read_text(encoding="utf-8")
    )
    chunks = load_chunks(args.chunks)
    coverage = benchmark_corpus_coverage(dataset, chunks)

    missing = []
    for case in dataset.cases:
        matches = coverage[case.id]
        status = "OK" if matches else "MISSING"
        print(f"{status:7} {case.id}: matches={len(matches)}")
        if not matches:
            missing.append(case.id)

    if missing:
        print(
            "\nCorpus coverage defect: "
            + ", ".join(missing)
            + "\n这些 Case 不能进入 Retriever 评分。"
        )
        raise SystemExit(1)

    print(
        f"\ncoverage=complete cases={len(dataset.cases)} "
        f"chunks={len(chunks):,}"
    )


if __name__ == "__main__":
    main()
