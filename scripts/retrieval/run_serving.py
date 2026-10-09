"""Run the local Poeticus Text Retrieval Service.

One process intentionally owns one resident copy of the model and FAISS indexes.
Do not increase uvicorn workers before measuring the memory multiplication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.data_paths import MODELS_ROOT, RETRIEVAL_ROOT

import uvicorn

from backend.retrieval.server import create_app
from backend.retrieval.serving import RetrievalServingRuntime
from backend.retrieval.serving_paths import default_paths

DEFAULT_DATA_ROOT = RETRIEVAL_ROOT
DEFAULT_MODEL_ROOT = MODELS_ROOT


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
