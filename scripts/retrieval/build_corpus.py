"""把外部 chinese-poetry 数据转换成统一 Work / Chunk JSONL。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from retrieval.corpus import build_chunks, load_chinese_poetry, write_jsonl
from retrieval.schema import ChunkPolicy


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "retrieval_corpus"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["chinese-poetry"],
        default="chinese-poetry",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dynasty")
    parser.add_argument("--genre")
    parser.add_argument(
        "--file-pattern",
        help=(
            "input 为目录时只读取匹配的顶层 JSON；"
            "例如 poet.tang.*.json / poet.song.*.json / ci.song.*.json"
        ),
    )
    parser.add_argument(
        "--chunk-policy",
        choices=["clause", "sentence", "clause_pair"],
        default="clause",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy: ChunkPolicy = args.chunk_policy

    works = load_chinese_poetry(
        args.input,
        dynasty=args.dynasty,
        genre=args.genre,
        file_pattern=args.file_pattern,
    )
    chunks = [
        chunk
        for work in works
        for chunk in build_chunks(work, policy)
    ]

    output_dir = args.output_dir
    works_path = output_dir / "works.jsonl"
    chunks_path = output_dir / f"chunks.{policy}.jsonl"
    manifest_path = output_dir / f"manifest.{policy}.json"

    write_jsonl(works, works_path)
    write_jsonl(chunks, chunks_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": args.source,
        "input": args.input.name,
        "dynasty": args.dynasty,
        "genre": args.genre,
        "file_pattern": args.file_pattern,
        "chunk_policy": policy,
        "work_count": len(works),
        "chunk_count": len(chunks),
        "works_file": works_path.name,
        "chunks_file": chunks_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"works:  {len(works):,} -> {works_path}")
    print(f"chunks: {len(chunks):,} -> {chunks_path}")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
