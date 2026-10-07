"""Profile character n-gram scale without building an index.

This is a cheap preflight for the lexical retrieval baseline. It scans Chunk
JSONL once and counts how many character n-gram occurrences the current
representation would generate. It does not build SQLite FTS5, allocate large
sets, or run any model.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.retrieval.lexical_bm25 import (
    CHUNK_PATHS,
    DEFAULT_MAX_N,
    DEFAULT_MIN_N,
    EXPECTED_CHUNKS,
    iter_character_runs,
)


def count_ngram_occurrences(
    text: str,
    *,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
) -> dict[int, int]:
    if min_n <= 0 or max_n < min_n:
        raise ValueError("n-gram 范围必须满足 0 < min_n <= max_n")

    counts = {n: 0 for n in range(min_n, max_n + 1)}
    for run in iter_character_runs(text):
        length = len(run)
        for n in counts:
            counts[n] += max(length - n + 1, 0)
    return counts


def profile_chunks(
    chunk_path: Path,
    *,
    min_n: int = DEFAULT_MIN_N,
    max_n: int = DEFAULT_MAX_N,
    expected_chunks: int | None = None,
) -> dict:
    chunk_path = chunk_path.expanduser().resolve()
    if not chunk_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{chunk_path}")

    started = time.perf_counter()
    chunks = 0
    text_characters = 0
    searchable_characters = 0
    zero_term_chunks = 0
    max_terms_per_chunk = 0
    by_n = {n: 0 for n in range(min_n, max_n + 1)}

    with chunk_path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行无法解析"
                ) from exc

            text = chunk.get("text")
            if not isinstance(text, str):
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行缺少有效 text"
                )

            chunks += 1
            text_characters += len(text)

            runs = list(iter_character_runs(text))
            searchable_characters += sum(len(run) for run in runs)

            counts = {n: 0 for n in by_n}
            for run in runs:
                length = len(run)
                for n in counts:
                    counts[n] += max(length - n + 1, 0)

            terms_this_chunk = sum(counts.values())
            if terms_this_chunk == 0:
                zero_term_chunks += 1
            max_terms_per_chunk = max(max_terms_per_chunk, terms_this_chunk)
            for n, count in counts.items():
                by_n[n] += count

    if expected_chunks is not None and chunks != expected_chunks:
        raise ValueError(
            f"Chunk 实际 {chunks:,} 条，预期 {expected_chunks:,} 条"
        )

    elapsed = time.perf_counter() - started
    total_terms = sum(by_n.values())
    return {
        "chunk_path": str(chunk_path),
        "chunks": chunks,
        "text_characters": text_characters,
        "searchable_characters": searchable_characters,
        "ngram_range": [min_n, max_n],
        "ngram_occurrences": {str(n): by_n[n] for n in sorted(by_n)},
        "total_ngram_occurrences": total_terms,
        "average_ngram_occurrences_per_chunk": (
            total_terms / chunks if chunks else 0.0
        ),
        "zero_term_chunks": zero_term_chunks,
        "max_ngram_occurrences_per_chunk": max_terms_per_chunk,
        "elapsed_seconds": elapsed,
        "chunks_per_second": chunks / elapsed if elapsed else None,
        "note": (
            "total_ngram_occurrences 是倒排索引需要处理的词项出现次数，"
            "不是 unique n-gram 数，也不是最终索引文件大小。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="统计 character n-gram lexical index 的全量规模"
    )
    parser.add_argument(
        "--chunk-policy",
        choices=sorted(CHUNK_PATHS),
        default="sentence",
    )
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--min-n", type=int, default=DEFAULT_MIN_N)
    parser.add_argument("--max-n", type=int, default=DEFAULT_MAX_N)
    parser.add_argument("--expected-chunks", type=int)
    args = parser.parse_args()

    chunk_path = args.chunks or CHUNK_PATHS[args.chunk_policy]
    expected_chunks = (
        args.expected_chunks
        if args.expected_chunks is not None
        else EXPECTED_CHUNKS[args.chunk_policy]
    )

    try:
        result = profile_chunks(
            chunk_path,
            min_n=args.min_n,
            max_n=args.max_n,
            expected_chunks=expected_chunks,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
