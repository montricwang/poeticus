"""Benchmark a compressed FAISS serving index against exact vector search.

The expensive Qwen embedding shards remain the canonical offline build asset.
This spike asks a narrower deployment question:

    How much can a serving ANN index shrink, and what exact-neighbor recall
    do we lose for that compression?

It samples vectors deterministically across the full Artifact, builds:
- IndexFlatIP as the exact reference on the same sample;
- IndexIVFPQ as the compressed ANN candidate.

The script reports measured sample index bytes plus a linear full-corpus size
projection. It does not modify the canonical Embedding Artifact.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Sequence

from scripts.retrieval.artifact_search import load_artifact_manifest

DEFAULT_SAMPLE_VECTORS = 100_000
DEFAULT_QUERY_COUNT = 50
DEFAULT_TOP_K = 20
DEFAULT_NLIST = 512
DEFAULT_PQ_M = 64
DEFAULT_PQ_BITS = 8
DEFAULT_NPROBES = (16, 32, 64, 128)


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "FAISS serving spike 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "FAISS serving spike 需要 faiss-cpu；"
            "请安装 requirements-retrieval.txt"
        ) from exc
    return faiss


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
    manifest: dict,
    rows,
):
    """Load only requested global rows from sharded .npy embeddings."""
    np = _require_numpy()

    rows = np.asarray(rows, dtype=np.int64)
    dimension = manifest["embedding_dimension"]
    vectors = np.empty((len(rows), dimension), dtype=np.float32)
    filled = np.zeros(len(rows), dtype=bool)

    for shard in manifest["completed_shards"]:
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


def choose_query_positions(sample_count: int, query_count: int):
    if sample_count <= 1:
        raise ValueError("sample_count 至少需要 2")
    if query_count <= 0:
        raise ValueError("query_count 必须为正整数")

    np = _require_numpy()
    count = min(query_count, sample_count)
    return np.unique(
        np.linspace(0, sample_count - 1, num=count, dtype=np.int64)
    )


def strip_self_neighbors(
    neighbor_ids,
    query_positions,
    *,
    top_k: int,
) -> list[list[int]]:
    """Remove each sampled query's own row and return the next top-k ids."""
    if top_k <= 0:
        raise ValueError("top_k 必须为正整数")

    output: list[list[int]] = []
    for row, self_id in zip(neighbor_ids, query_positions, strict=True):
        kept = [int(item) for item in row if int(item) >= 0 and int(item) != int(self_id)]
        output.append(kept[:top_k])
    return output


def recall_at_k(
    exact_neighbors: Sequence[Sequence[int]],
    ann_neighbors: Sequence[Sequence[int]],
    *,
    top_k: int,
) -> float:
    if len(exact_neighbors) != len(ann_neighbors):
        raise ValueError("Exact / ANN query 数量不一致")
    if not exact_neighbors:
        return 0.0

    total = 0.0
    for exact, ann in zip(exact_neighbors, ann_neighbors, strict=True):
        expected = set(exact[:top_k])
        if not expected:
            continue
        total += len(expected.intersection(ann[:top_k])) / len(expected)
    return total / len(exact_neighbors)


def project_full_index_bytes(
    *,
    trained_empty_bytes: int,
    populated_sample_bytes: int,
    sample_vectors: int,
    full_vectors: int,
) -> int:
    """Project full index bytes from measured fixed + per-vector sample cost."""
    if sample_vectors <= 0 or full_vectors <= 0:
        raise ValueError("vector count 必须为正整数")
    if populated_sample_bytes < trained_empty_bytes:
        raise ValueError("sample index bytes 不能小于 empty index bytes")

    per_vector = (
        populated_sample_bytes - trained_empty_bytes
    ) / sample_vectors
    return int(math.ceil(trained_empty_bytes + per_vector * full_vectors))


def _mib(value: int | float) -> float:
    return float(value) / (1024 * 1024)


def _gib(value: int | float) -> float:
    return float(value) / (1024 * 1024 * 1024)


def _search_latency_ms_per_query(index, queries, search_k: int) -> float:
    # Warm one batch to avoid counting first-call setup.
    index.search(queries[: min(len(queries), 4)], search_k)
    started = time.perf_counter()
    index.search(queries, search_k)
    elapsed = time.perf_counter() - started
    return elapsed * 1000 / len(queries)


def normalize_nprobes(
    nprobes: Sequence[int],
    *,
    nlist: int,
) -> list[int]:
    """Clamp nprobe values to nlist and keep first-seen order."""
    if nlist <= 0:
        raise ValueError("nlist 必须为正整数")
    if not nprobes:
        raise ValueError("至少需要一个 nprobe")

    output: list[int] = []
    for value in nprobes:
        if value <= 0:
            raise ValueError("nprobe 必须为正整数")
        actual = min(value, nlist)
        if actual not in output:
            output.append(actual)
    return output


def benchmark_artifact(
    artifact_dir: Path,
    *,
    sample_vectors: int,
    query_count: int,
    top_k: int,
    nlist: int,
    pq_m: int,
    pq_bits: int,
    nprobes: Sequence[int],
    threads: int | None,
) -> dict:
    np = _require_numpy()
    faiss = _require_faiss()

    artifact_dir = artifact_dir.expanduser().resolve()
    manifest = load_artifact_manifest(artifact_dir)

    dimension = manifest["embedding_dimension"]
    total_vectors = manifest["completed_chunks"]

    if dimension % pq_m != 0:
        raise ValueError(
            f"dimension={dimension} 不能被 pq_m={pq_m} 整除"
        )
    if pq_m <= 0 or pq_bits <= 0:
        raise ValueError("FAISS 参数必须为正整数")
    normalized_nprobes = normalize_nprobes(nprobes, nlist=nlist)

    if threads is not None:
        if threads <= 0:
            raise ValueError("threads 必须为正整数")
        faiss.omp_set_num_threads(threads)

    sampled_rows = sample_global_rows(total_vectors, sample_vectors)
    vectors = load_sampled_vectors(artifact_dir, manifest, sampled_rows)

    if len(vectors) <= nlist:
        raise ValueError(
            f"sample_vectors={len(vectors)} 必须明显大于 nlist={nlist}"
        )

    query_positions = choose_query_positions(len(vectors), query_count)
    queries = np.ascontiguousarray(vectors[query_positions], dtype=np.float32)
    database = np.ascontiguousarray(vectors, dtype=np.float32)

    search_k = min(len(database), top_k + 8)

    exact = faiss.IndexFlatIP(dimension)
    exact.add(database)
    exact_latency = _search_latency_ms_per_query(exact, queries, search_k)
    _, exact_ids = exact.search(queries, search_k)
    exact_neighbors = strip_self_neighbors(
        exact_ids,
        query_positions,
        top_k=top_k,
    )

    quantizer = faiss.IndexFlatIP(dimension)
    ann = faiss.IndexIVFPQ(
        quantizer,
        dimension,
        nlist,
        pq_m,
        pq_bits,
        faiss.METRIC_INNER_PRODUCT,
    )

    training_count = min(
        len(database),
        max(nlist * 40, min(len(database), 50_000)),
    )
    training_positions = np.linspace(
        0,
        len(database) - 1,
        num=training_count,
        dtype=np.int64,
    )
    training = np.ascontiguousarray(
        database[training_positions],
        dtype=np.float32,
    )

    started = time.perf_counter()
    ann.train(training)
    train_seconds = time.perf_counter() - started

    empty_bytes = len(faiss.serialize_index(ann))

    started = time.perf_counter()
    ann.add(database)
    add_seconds = time.perf_counter() - started

    nprobe_sweep = []
    for nprobe in normalized_nprobes:
        ann.nprobe = nprobe
        ann_latency = _search_latency_ms_per_query(ann, queries, search_k)
        _, ann_ids = ann.search(queries, search_k)
        ann_neighbors = strip_self_neighbors(
            ann_ids,
            query_positions,
            top_k=top_k,
        )
        nprobe_sweep.append(
            {
                "nprobe": nprobe,
                "recall_at_k_vs_exact": recall_at_k(
                    exact_neighbors,
                    ann_neighbors,
                    top_k=top_k,
                ),
                "latency_ms_per_query_sample": ann_latency,
            }
        )

    baseline = nprobe_sweep[0]
    populated_bytes = len(faiss.serialize_index(ann))
    projected_bytes = project_full_index_bytes(
        trained_empty_bytes=empty_bytes,
        populated_sample_bytes=populated_bytes,
        sample_vectors=len(database),
        full_vectors=total_vectors,
    )

    raw_float16_bytes = total_vectors * dimension * 2
    raw_float32_bytes = total_vectors * dimension * 4

    return {
        "artifact_dir": str(artifact_dir),
        "model": manifest["model"],
        "chunk_policy": manifest["chunk_policy"],
        "dimension": dimension,
        "corpus_vectors": total_vectors,
        "sample_vectors": len(database),
        "query_vectors": len(queries),
        "top_k": top_k,
        "exact_reference": {
            "engine": "faiss_IndexFlatIP",
            "latency_ms_per_query_sample": exact_latency,
        },
        "compressed_candidate": {
            "engine": "faiss_IndexIVFPQ",
            "nlist": nlist,
            "pq_m": pq_m,
            "pq_bits": pq_bits,
            "nprobe": baseline["nprobe"],
            "training_vectors": training_count,
            "training_seconds": train_seconds,
            "add_seconds": add_seconds,
            "recall_at_k_vs_exact": baseline["recall_at_k_vs_exact"],
            "latency_ms_per_query_sample": baseline[
                "latency_ms_per_query_sample"
            ],
            "nprobe_sweep": nprobe_sweep,
            "trained_empty_index_bytes": empty_bytes,
            "sample_index_bytes": populated_bytes,
            "sample_index_mib": _mib(populated_bytes),
            "projected_full_index_bytes": projected_bytes,
            "projected_full_index_gib": _gib(projected_bytes),
        },
        "raw_embedding_reference": {
            "float16_bytes": raw_float16_bytes,
            "float16_gib": _gib(raw_float16_bytes),
            "float32_bytes": raw_float32_bytes,
            "float32_gib": _gib(raw_float32_bytes),
        },
        "note": (
            "这是 serving-index spike：Recall 只衡量 ANN 是否复现 Exact "
            "vector neighbors，不衡量文学关系正确率。Full size 为基于 sample "
            "serialized bytes 的线性投影，正式部署前仍需 full build 验证。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="比较 Exact FAISS 与压缩 IVFPQ serving index"
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        action="append",
        required=True,
        help="可重复传入 sentence / clause Embedding Artifact",
    )
    parser.add_argument(
        "--sample-vectors",
        type=int,
        default=DEFAULT_SAMPLE_VECTORS,
    )
    parser.add_argument("--query-count", type=int, default=DEFAULT_QUERY_COUNT)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--nlist", type=int, default=DEFAULT_NLIST)
    parser.add_argument("--pq-m", type=int, default=DEFAULT_PQ_M)
    parser.add_argument("--pq-bits", type=int, default=DEFAULT_PQ_BITS)
    parser.add_argument(
        "--nprobe",
        dest="nprobes",
        type=int,
        action="append",
        help=(
            "可重复传入；默认依次测试 16 / 32 / 64 / 128，"
            "同一 IVFPQ index 只训练和 add 一次"
        ),
    )
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()

    results = [
        benchmark_artifact(
            artifact_dir,
            sample_vectors=args.sample_vectors,
            query_count=args.query_count,
            top_k=args.top_k,
            nlist=args.nlist,
            pq_m=args.pq_m,
            pq_bits=args.pq_bits,
            nprobes=args.nprobes or DEFAULT_NPROBES,
            threads=args.threads,
        )
        for artifact_dir in args.artifact_dir
    ]

    print(
        json.dumps(
            {
                "status": "complete",
                "artifacts": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
