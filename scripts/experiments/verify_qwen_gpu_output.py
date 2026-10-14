#!/usr/bin/env python3
"""Check AutoDL-produced Qwen embeddings against the local reading corpus."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def verify_output(data_dir: Path, corpus_path: Path) -> tuple[np.ndarray, str]:
    """Return vectors and SHA256 after validating the AutoDL transfer and row mapping."""
    filename = "qwen3_all_3491"
    matrix_path = data_dir / f"{filename}.npy"
    metadata_path = data_dir / f"{filename}_manifest.json"
    prepared_input = data_dir / "qwen_gpu_input.jsonl"
    manifest = json.loads(metadata_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    source_ids = [work["id"] for work in corpus]

    if manifest["source_ids"] != source_ids:
        raise ValueError("AutoDL vector rows do not match source corpus order")
    if (
        hashlib.sha256(prepared_input.read_bytes()).hexdigest()
        != manifest["input_sha256"]
    ):
        raise ValueError("AutoDL input checksum mismatch")
    vector_sha256 = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    if vector_sha256 != manifest["file_sha256"]:
        raise ValueError("Downloaded vector file checksum mismatch")

    matrix = np.load(matrix_path, allow_pickle=False)
    if matrix.shape != (len(source_ids), 1024) or matrix.dtype != np.float32:
        raise ValueError(f"Unexpected shape/dtype: {matrix.shape}, {matrix.dtype}")
    if not np.isfinite(matrix).all():
        raise ValueError("Nonfinite vectors")
    if not np.allclose(np.linalg.norm(matrix, axis=1), 1, atol=0.0003):
        raise ValueError("Vectors are not normalized")
    return matrix, vector_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    matrix, _ = verify_output(args.data_dir, args.corpus)
    print(
        "PASS",
        matrix.shape,
        "ordered source IDs, file hashes, finite normalized vectors",
    )


if __name__ == "__main__":
    main()
