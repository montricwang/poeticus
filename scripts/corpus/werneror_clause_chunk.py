"""Build clause-level Werneror Retrieval chunks.

Run from the Poeticus repository root:

    python -m scripts.corpus.werneror_clause_chunk
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.corpus.werneror_chunk import (
    DEFAULT_EXPECTED_WORKS,
    build_clause_chunks,
)

DEFAULT_INPUT = Path("../poeticus-data/output/retrieval/werneror_works.jsonl")
DEFAULT_OUTPUT = Path(
    "../poeticus-data/output/retrieval/werneror_chunks_clause.jsonl"
)
DEFAULT_REPORT = Path(
    "../poeticus-data/output/retrieval/werneror_clause_chunks.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Werneror Work JSONL -> clause Chunk JSONL"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--expect-works", type=int, default=DEFAULT_EXPECTED_WORKS
    )
    parser.add_argument(
        "--expect-chunks",
        type=int,
        default=0,
        help="预期 Chunk 数；0 表示只按实际结果生成并报告",
    )
    args = parser.parse_args()

    report = build_clause_chunks(
        args.input,
        args.output,
        args.report,
        expected_works=args.expect_works or None,
        expected_chunks=args.expect_chunks or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
