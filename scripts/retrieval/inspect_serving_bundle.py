"""Inspect the exact runtime artifacts required by Retrieval Serving."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.data_paths import MODELS_ROOT, RETRIEVAL_ROOT
from backend.retrieval.serving_paths import default_paths

DEFAULT_DATA_ROOT = RETRIEVAL_ROOT
DEFAULT_MODEL_ROOT = MODELS_ROOT


def path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(
            item.stat().st_size
            for item in path.rglob("*")
            if item.is_file()
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="列出 Retrieval Serving 真正需要上传的 runtime artifacts"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
    )
    args = parser.parse_args()

    paths = default_paths(args.data_root, args.model_root)
    items = {
        "sentence_embedding_manifest": (
            paths.sentence_embedding_dir / "manifest.json"
        ),
        "clause_embedding_manifest": (
            paths.clause_embedding_dir / "manifest.json"
        ),
        "sentence_faiss": paths.sentence_faiss_dir,
        "clause_faiss": paths.clause_faiss_dir,
        "sentence_bm25": paths.bm25_sentence_dir,
        "metadata_db": paths.metadata_db,
        "metadata_manifest": paths.metadata_db.with_suffix(
            ".manifest.json"
        ),
        "qwen_model": paths.model_path,
    }

    missing = [
        name
        for name, path in items.items()
        if not path.exists()
    ]
    if missing:
        raise SystemExit(
            "Serving bundle 缺少 artifact："
            + ", ".join(missing)
        )

    entries = []
    total = 0
    for name, path in items.items():
        size = path_size(path)
        total += size
        entries.append(
            {
                "name": name,
                "path": str(path.resolve()),
                "bytes": size,
                "gib": size / (1024 ** 3),
            }
        )

    print(
        json.dumps(
            {
                "schema_version": "1",
                "items": entries,
                "total_bytes": total,
                "total_gib": total / (1024 ** 3),
                "note": (
                    "Raw embedding shards and source Corpus JSONL are "
                    "intentionally not part of the Serving bundle."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
