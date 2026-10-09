"""Build the compact SQLite metadata store used by Retrieval Serving."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_ROOT

from backend.retrieval.metadata_store import build_metadata_store
DEFAULT_DATA_ROOT = RETRIEVAL_ROOT
DEFAULT_WORKS = RETRIEVAL_CORPUS_ROOT / "werneror_works.jsonl"

DEFAULT_SENTENCE_CHUNKS = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_sentence.jsonl"
DEFAULT_CLAUSE_CHUNKS = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_clause.jsonl"
DEFAULT_OUTPUT = DEFAULT_DATA_ROOT / "serving/retrieval_metadata.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="建立 Retrieval Serving compact metadata SQLite"
    )
    parser.add_argument("--works", type=Path, default=DEFAULT_WORKS)
    parser.add_argument(
        "--sentence-chunks",
        type=Path,
        default=DEFAULT_SENTENCE_CHUNKS,
    )
    parser.add_argument(
        "--clause-chunks",
        type=Path,
        default=DEFAULT_CLAUSE_CHUNKS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        result = build_metadata_store(
            work_path=args.works,
            sentence_chunk_path=args.sentence_chunks,
            clause_chunk_path=args.clause_chunks,
            output_path=args.output,
            batch_size=args.batch_size,
            force=args.force,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
