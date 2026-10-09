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
from scripts.retrieval.vector_sampling import load_sampled_vectors, sample_global_rows

DEFAULT_SAMPLE_VECTORS = 100_000
DEFAULT_QUERY_COUNT = 50
DEFAULT_TOP_K = 20
DEFAULT_NLIST = 512
DEFAULT_PQ_MS = (64, 128, 256)
DEFAULT_PQ_BITS = 8
DEFAULT_NPROBES = (64,)


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


def normalize_pq_ms(
    pq_ms: Sequence[int],
    *,
    dimension: int,
) -> list[int]:
    """Validate PQ subquantizer counts and keep first-seen order."""
    if not pq_ms:
        raise ValueError("至少需要一个 pq_m")

    output: list[int] = []
    for value in pq_ms:
        if value <= 0:
            raise ValueError("pq_m 必须为正整数")
        if dimension % value != 0:
            raise ValueError(
                f"dimension={dimension} 不能被 pq_m={value} 整除"
            )
        if value not in output:
            output.append(value)
    return output


def benchmark_artifact(
    artifact_dir: Path,
    *,
    sample_vectors: int,
    query_count: int,
    top_k: int,
    nlist: int,
    pq_ms: Sequence[int],
    pq_bits: int,
    nprobes: Sequence[int],
    threads: int | None,
) -> dict[str, object]:
    np = _require_numpy()
    faiss = _require_faiss()

    artifact_dir = artifact_dir.expanduser().resolve()
    manifest = load_artifact_manifest(artifact_dir)

    dimension = manifest["embedding_dimension"]
    total_vectors = manifest["completed_chunks"]

    if pq_bits <= 0:
        raise ValueError("FAISS 参数必须为正整数")
    normalized_pq_ms = normalize_pq_ms(pq_ms, dimension=dimension)
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

    compression_sweep = []
    for pq_m in normalized_pq_ms:
        quantizer = faiss.IndexFlatIP(dimension)
        ann = faiss.IndexIVFPQ(
            quantizer,
            dimension,
            nlist,
            pq_m,
            pq_bits,
            faiss.METRIC_INNER_PRODUCT,
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
            ann_latency = _search_latency_ms_per_query(
                ann,
                queries,
                search_k,
            )
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

        compression_sweep.append(
            {
                "engine": "faiss_IndexIVFPQ",
                "nlist": nlist,
                "pq_m": pq_m,
                "pq_bits": pq_bits,
                "nprobe": baseline["nprobe"],
                "training_vectors": training_count,
                "training_seconds": train_seconds,
                "add_seconds": add_seconds,
                "recall_at_k_vs_exact": baseline[
                    "recall_at_k_vs_exact"
                ],
                "latency_ms_per_query_sample": baseline[
                    "latency_ms_per_query_sample"
                ],
                "nprobe_sweep": nprobe_sweep,
                "trained_empty_index_bytes": empty_bytes,
                "sample_index_bytes": populated_bytes,
                "sample_index_mib": _mib(populated_bytes),
                "projected_full_index_bytes": projected_bytes,
                "projected_full_index_gib": _gib(projected_bytes),
            }
        )

        del ann
        del quantizer

    baseline_candidate = compression_sweep[0]
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
        "compressed_candidate": baseline_candidate,
        "compression_sweep": compression_sweep,
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
    parser.add_argument(
        "--pq-m",
        dest="pq_ms",
        type=int,
        action="append",
        help=(
            "可重复传入；默认依次测试 64 / 128 / 256，"
            "用于比较压缩强度与 Recall / footprint 的取舍"
        ),
    )
    parser.add_argument("--pq-bits", type=int, default=DEFAULT_PQ_BITS)
    parser.add_argument(
        "--nprobe",
        dest="nprobes",
        type=int,
        action="append",
        help=(
            "可重复传入；默认只测试 64。上一轮已经证明继续增大 "
            "nprobe 几乎不改善 Recall；如需复现实验可显式重复传入"
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
            pq_ms=args.pq_ms or DEFAULT_PQ_MS,
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
