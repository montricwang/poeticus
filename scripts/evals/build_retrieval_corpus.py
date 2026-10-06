"""把本地 chinese-poetry JSON 转成统一 Retrieval corpus。"""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.retrieval_corpus import (
    chunks_for_work,
    load_chinese_poetry_file,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build parent works and retrieval chunks from chinese-poetry JSON."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dynasty")
    parser.add_argument(
        "--policy",
        choices=["clause", "sentence", "clause_pair"],
        required=True,
    )
    parser.add_argument(
        "--source",
        default="chinese-poetry/chinese-poetry",
    )
    parser.add_argument("--works-output", type=Path, required=True)
    parser.add_argument("--chunks-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    works = load_chinese_poetry_file(
        args.input,
        source=args.source,
        dynasty=args.dynasty,
    )
    chunks = [
        chunk
        for work in works
        for chunk in chunks_for_work(work, args.policy)
    ]

    write_jsonl(works, args.works_output)
    write_jsonl(chunks, args.chunks_output)

    print(
        f"works={len(works)} chunks={len(chunks)} "
        f"policy={args.policy} source={args.source}"
    )
    print(f"works_output={args.works_output}")
    print(f"chunks_output={args.chunks_output}")


if __name__ == "__main__":
    main()
