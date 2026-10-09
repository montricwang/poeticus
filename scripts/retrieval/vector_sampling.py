"""Read deterministic representative rows from sharded Embedding artifacts.

These functions belong to the FAISS build pipeline, not to a one-time
compression experiment. Importing them does not load a model or FAISS.
"""
from pathlib import Path
from collections.abc import Mapping
from typing import TypedDict

from pydantic import TypeAdapter



class VectorShard(TypedDict):
    start: int
    end: int
    file: str


class VectorShardManifest(TypedDict):
    embedding_dimension: int
    completed_shards: list[VectorShard]


_VECTOR_MANIFEST_ADAPTER = TypeAdapter(VectorShardManifest)


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "向量采样需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def sample_global_rows(total: int, sample_size: int):
    """Return deterministic, corpus-wide row ids for a representative sample."""
    if total <= 0:
        raise ValueError("total 必须为正整数")
    if sample_size <= 0:
        raise ValueError("sample_size 必须为正整数")

    np = _require_numpy()
    size = min(total, sample_size)
    if size == total:
        return np.arange(total, dtype=np.int64)

    rows = np.linspace(0, total - 1, num=size, dtype=np.int64)
    return np.unique(rows)


def load_sampled_vectors(
    artifact_dir: Path,
    manifest: Mapping[str, object],
    rows,
):
    """Load only requested global rows from sharded .npy embeddings."""
    np = _require_numpy()

    rows = np.asarray(rows, dtype=np.int64)
    shard_manifest = _VECTOR_MANIFEST_ADAPTER.validate_python(manifest)
    dimension = shard_manifest["embedding_dimension"]
    vectors = np.empty((len(rows), dimension), dtype=np.float32)
    filled = np.zeros(len(rows), dtype=bool)

    for shard in shard_manifest["completed_shards"]:
        start = shard["start"]
        end = shard["end"]

        positions = np.flatnonzero((rows >= start) & (rows < end))
        if positions.size == 0:
            continue

        shard_path = artifact_dir / shard["file"]
        matrix = np.load(shard_path, mmap_mode="r")
        local_rows = rows[positions] - start

        vectors[positions] = np.asarray(matrix[local_rows], dtype=np.float32)
        filled[positions] = True

    if not bool(filled.all()):
        missing = rows[~filled][:10].tolist()
        raise ValueError(f"Embedding Artifact 缺少采样 row：{missing}")

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if bool((norms == 0).any()):
        raise ValueError("采样 Embedding 中存在零向量")
    vectors /= norms
    return vectors


