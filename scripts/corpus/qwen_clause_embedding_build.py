"""Build the canonical Qwen clause-level Retrieval artifact.

This wrapper freezes the comparison settings established by the Retrieval Eval:
- Werneror clause corpus
- Qwen3-Embedding-0.6B
- 1024 dimensions
- normalized float16 shards
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.corpus.qwen_embedding_build import build_embeddings

DEFAULT_INPUT = Path(
    "../poeticus-data/output/retrieval/werneror_chunks_clause.jsonl"
)
DEFAULT_OUTPUT_DIR = Path(
    "../poeticus-data/output/retrieval/embeddings/qwen3_0.6b_clause_1024"
)
DEFAULT_EXPECTED_CHUNKS = 9_425_173
DEFAULT_DIMENSION = 1024
DEFAULT_BATCH_SIZE = 64
DEFAULT_SHARD_SIZE = 10_000


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成 Werneror clause Corpus 的 Qwen 1024d Embedding"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument(
        "--expected-chunks", type=int, default=DEFAULT_EXPECTED_CHUNKS
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    build_embeddings(
        input_path=args.input,
        output_dir=args.output_dir,
        model_path=args.model_path.expanduser().resolve(),
        dimension=DEFAULT_DIMENSION,
        batch_size=args.batch_size,
        shard_size=args.shard_size,
        expected_chunks=args.expected_chunks,
        device=args.device,
        chunk_policy="clause",
    )


if __name__ == "__main__":
    main()
