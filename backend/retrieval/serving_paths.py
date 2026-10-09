"""Resolve the local artifact bundle consumed by Retrieval Serving.

The service launcher, bundle inspector and benchmark must agree on the exact
index and model paths. This module does not start a server or load the model.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.retrieval.serving import ServingPaths


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


