"""Run the local Poeticus Text Retrieval Service.

One process intentionally owns one resident copy of the model and FAISS indexes.
Do not increase uvicorn workers before measuring the memory multiplication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import uvicorn

from backend.retrieval.server import create_app
from backend.retrieval.serving import (
    RetrievalServingRuntime,
    ServingPaths,
)

DEFAULT_DATA_ROOT = Path("../poeticus-data/output/retrieval")
DEFAULT_MODEL_ROOT = Path("../poeticus-data/models")


def default_paths(
    data_root: Path,
    model_root: Path,
) -> ServingPaths:
    data_root = data_root.expanduser().resolve()
    model_root = model_root.expanduser().resolve()

    sentence_embedding = (
        data_root / "embeddings/qwen3_0.6b_sentence_1024"
    )
    manifest = json.loads(
        (sentence_embedding / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    fingerprint = manifest.get("model_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError(
            "sentence Embedding manifest 缺少 model_fingerprint"
        )

    return ServingPaths(
        sentence_embedding_dir=sentence_embedding,
        sentence_faiss_dir=(
            data_root
            / "faiss/qwen3_0.6b_sentence_1024_ivfpq_nlist512_m256_b8"
        ),
        clause_embedding_dir=(
            data_root / "embeddings/qwen3_0.6b_clause_1024"
        ),
        clause_faiss_dir=(
            data_root
            / "faiss/qwen3_0.6b_clause_1024_ivfpq_nlist512_m256_b8"
        ),
        bm25_sentence_dir=(
            data_root / "lexical/bm25_sentence_2_3"
        ),
        metadata_db=(
            data_root / "serving/retrieval_metadata.sqlite3"
        ),
        model_path=(
            model_root
            / f"Qwen3-Embedding-0.6B-{fingerprint[:12]}"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="启动本地 Poeticus Text Retrieval Service"
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
    parser.add_argument("--device")
    parser.add_argument("--search-k", type=int, default=100)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--api-token",
        default=os.getenv("POETICUS_TEXT_RETRIEVAL_TOKEN", ""),
    )
    args = parser.parse_args()

    paths = default_paths(
        args.data_root,
        args.model_root,
    )
    runtime = RetrievalServingRuntime(
        paths,
        device=args.device,
        search_k=args.search_k,
        rrf_k=args.rrf_k,
    )
    app = create_app(
        runtime,
        api_token=args.api_token,
    )

    print(
        json.dumps(
            {
                "status": "ready",
                "host": args.host,
                "port": args.port,
                "startup_profile": runtime.startup_profile,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,
    )


if __name__ == "__main__":
    main()
