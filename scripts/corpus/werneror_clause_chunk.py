"""Build clause-level Werneror Retrieval chunks.

Run from the Poeticus repository root:

    python -m scripts.corpus.werneror_clause_chunk
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_REPORTS_ROOT

from scripts.corpus.werneror_chunk import (
    DEFAULT_EXPECTED_WORKS,
    build_clause_chunks,
)

DEFAULT_INPUT = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"
DEFAULT_OUTPUT = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_clause.jsonl"
DEFAULT_REPORT = RETRIEVAL_REPORTS_ROOT / "werneror_clause_chunks.json"
DEFAULT_EXPECTED_CHUNKS = 9_425_173


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
        default=DEFAULT_EXPECTED_CHUNKS,
        help="预期 Clause Chunk 数；传 0 可关闭数量校验",
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
