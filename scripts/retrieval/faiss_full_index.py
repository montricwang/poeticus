"""Build a full FAISS IVFPQ serving index from an Embedding Artifact.

The raw float16 Embedding Artifact remains the canonical offline build asset.
This script trains one IVFPQ index and then adds every embedding shard in
global-row order. FAISS implicit ids therefore stay identical to Chunk JSONL
logical row ids:

    FAISS id == embedding global row == Chunk JSONL logical row

No second row-id mapping artifact is needed.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from scripts.retrieval.artifact_search import load_artifact_manifest
from scripts.retrieval.faiss_serving_spike import (
    load_sampled_vectors,
    sample_global_rows,
)

DEFAULT_OUTPUT_ROOT = Path("../poeticus-data/output/retrieval/faiss")
DEFAULT_NLIST = 512
DEFAULT_PQ_M = 256
DEFAULT_PQ_BITS = 8
DEFAULT_NPROBE = 64
DEFAULT_TRAINING_VECTORS = 50_000
INDEX_FILENAME = "index.faiss"
MANIFEST_FILENAME = "manifest.json"
INDEX_MANIFEST_VERSION = 1


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "FAISS full index build 需要 NumPy；请安装 requirements-retrieval.txt"
        ) from exc
    return np


def _require_faiss():
    try:
        import faiss
    except ImportError as exc:
        raise RuntimeError(
            "FAISS full index build 需要 faiss-cpu；"
            "请安装 requirements-retrieval.txt"
        ) from exc
    return faiss


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def index_dir_name(
    artifact_dir: Path,
    *,
    nlist: int,
    pq_m: int,
    pq_bits: int,
) -> str:
    return (
        f"{artifact_dir.name}_ivfpq_"
        f"nlist{nlist}_m{pq_m}_b{pq_bits}"
    )


def source_signature(embedding_manifest: dict) -> dict:
    keys = (
        "model",
        "model_fingerprint",
        "input_sha256",
        "chunk_policy",
        "embedding_dimension",
        "dtype",
        "normalized",
        "completed_chunks",
    )
    missing = [key for key in keys if key not in embedding_manifest]
    if missing:
        raise ValueError(
            "Embedding manifest 缺少 serving index 所需字段："
            + ", ".join(missing)
        )
    return {key: embedding_manifest[key] for key in keys}


def build_signature(
    embedding_manifest: dict,
    *,
    nlist: int,
    pq_m: int,
    pq_bits: int,
    nprobe: int,
    training_vectors: int,
) -> dict:
    dimension = embedding_manifest["embedding_dimension"]
    if nlist <= 0 or pq_m <= 0 or pq_bits <= 0 or nprobe <= 0:
        raise ValueError("FAISS 参数必须为正整数")
    if training_vectors <= 0:
        raise ValueError("training_vectors 必须为正整数")
    if dimension % pq_m != 0:
        raise ValueError(
            f"dimension={dimension} 不能被 pq_m={pq_m} 整除"
        )
    if not embedding_manifest.get("normalized"):
        raise ValueError("当前 Inner Product serving index 要求 normalized Embedding")

    return {
        "manifest_version": INDEX_MANIFEST_VERSION,
        "engine": "faiss_IndexIVFPQ",
        "source_embedding": source_signature(embedding_manifest),
        "nlist": nlist,
        "pq_m": pq_m,
        "pq_bits": pq_bits,
        "nprobe": min(nprobe, nlist),
        "training_vectors": min(
            training_vectors,
            embedding_manifest["completed_chunks"],
        ),
        "row_id_contract": (
            "faiss_id == embedding_global_row == chunk_jsonl_logical_row"
        ),
    }


def assert_compatible_manifest(manifest: dict, signature: dict) -> None:
    mismatches = []
    for key, expected in signature.items():
        actual = manifest.get(key)
        if actual != expected:
            mismatches.append(f"{key}: 已有={actual!r}, 本次={expected!r}")
    if mismatches:
        raise ValueError(
            "已有 FAISS index manifest 与本次参数不兼容；"
            "请换新输出目录，不要覆盖旧 index。\n"
            + "\n".join(mismatches)
        )


def write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _validate_shard(matrix, *, rows: int, dimension: int, path: Path) -> None:
    expected_shape = (rows, dimension)
    if matrix.shape != expected_shape:
        raise ValueError(
            f"{path.name} shape={matrix.shape}，预期 {expected_shape}"
        )
    if str(matrix.dtype) != "float16":
        raise ValueError(
            f"{path.name} dtype={matrix.dtype}，预期 float16"
        )


def build_full_index(
    artifact_dir: Path,
    *,
    output_dir: Path,
    nlist: int = DEFAULT_NLIST,
    pq_m: int = DEFAULT_PQ_M,
    pq_bits: int = DEFAULT_PQ_BITS,
    nprobe: int = DEFAULT_NPROBE,
    training_vectors: int = DEFAULT_TRAINING_VECTORS,
    threads: int | None = None,
) -> dict:
    np = _require_numpy()
    faiss = _require_faiss()

    artifact_dir = artifact_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    embedding_manifest = load_artifact_manifest(artifact_dir)
    signature = build_signature(
        embedding_manifest,
        nlist=nlist,
        pq_m=pq_m,
        pq_bits=pq_bits,
        nprobe=nprobe,
        training_vectors=training_vectors,
    )

    if threads is not None:
        if threads <= 0:
            raise ValueError("threads 必须为正整数")
        faiss.omp_set_num_threads(threads)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_FILENAME
    index_path = output_dir / INDEX_FILENAME

    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert_compatible_manifest(existing, signature)
        if existing.get("status") == "complete" and index_path.is_file():
            actual_bytes = index_path.stat().st_size
            if actual_bytes != existing.get("index_bytes"):
                raise ValueError(
                    "FAISS index 文件大小与 manifest 不一致："
                    f"manifest={existing.get('index_bytes')}, "
                    f"actual={actual_bytes}"
                )
            print(f"FAISS full index 已存在：{index_path}", flush=True)
            return existing
        raise ValueError(
            f"输出目录存在未完成的构建：{output_dir}；"
            "请确认旧构建不再需要后删除该目录，再重新运行"
        )

    leftovers = [path.name for path in output_dir.iterdir()]
    if leftovers:
        raise ValueError(
            f"输出目录已有文件但没有 manifest：{output_dir}；"
            "请换新目录，避免混入旧结果"
        )

    running_manifest = {
        **signature,
        "status": "running",
        "source_artifact_dir": str(artifact_dir),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    write_json_atomic(manifest_path, running_manifest)

    dimension = embedding_manifest["embedding_dimension"]
    total_vectors = embedding_manifest["completed_chunks"]
    actual_training_vectors = signature["training_vectors"]

    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "output_dir": str(output_dir),
                "chunk_policy": embedding_manifest["chunk_policy"],
                "dimension": dimension,
                "corpus_vectors": total_vectors,
                "nlist": nlist,
                "pq_m": pq_m,
                "pq_bits": pq_bits,
                "nprobe": signature["nprobe"],
                "training_vectors": actual_training_vectors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    training_rows = sample_global_rows(
        total_vectors,
        actual_training_vectors,
    )
    training = load_sampled_vectors(
        artifact_dir,
        embedding_manifest,
        training_rows,
    )
    training = np.ascontiguousarray(training, dtype=np.float32)

    quantizer = faiss.IndexFlatIP(dimension)
    index = faiss.IndexIVFPQ(
        quantizer,
        dimension,
        nlist,
        pq_m,
        pq_bits,
        faiss.METRIC_INNER_PRODUCT,
    )

    print("训练 IVFPQ……", flush=True)
    started = time.perf_counter()
    index.train(training)
    training_seconds = time.perf_counter() - started
    del training

    print("加入全部 Embedding shards……", flush=True)
    add_started = time.perf_counter()
    shards = embedding_manifest["completed_shards"]
    for shard_no, item in enumerate(shards, 1):
        path = artifact_dir / item["file"]
        matrix = np.load(path, mmap_mode="r", allow_pickle=False)
        rows = item["end"] - item["start"]
        _validate_shard(
            matrix,
            rows=rows,
            dimension=dimension,
            path=path,
        )

        batch = np.ascontiguousarray(matrix, dtype=np.float32)
        index.add(batch)
        del batch
        del matrix

        if index.ntotal != item["end"]:
            raise RuntimeError(
                "FAISS implicit row id 已与 Embedding global row 漂移："
                f"ntotal={index.ntotal}, expected={item['end']}"
            )

        print(
            f"Add shards: {shard_no}/{len(shards)} "
            f"({index.ntotal:,}/{total_vectors:,})",
            end="\r",
            flush=True,
        )

    print(" " * 100, end="\r", flush=True)
    add_seconds = time.perf_counter() - add_started
    index.nprobe = signature["nprobe"]

    tmp_index_path = index_path.with_name(index_path.name + ".tmp")
    print("写入完整 FAISS index……", flush=True)
    write_started = time.perf_counter()
    faiss.write_index(index, str(tmp_index_path))
    os.replace(tmp_index_path, index_path)
    write_seconds = time.perf_counter() - write_started
    index_bytes = index_path.stat().st_size

    result = {
        **signature,
        "status": "complete",
        "source_artifact_dir": str(artifact_dir),
        "created_at": running_manifest["created_at"],
        "updated_at": utc_now(),
        "index_file": INDEX_FILENAME,
        "index_bytes": index_bytes,
        "index_gib": index_bytes / (1024 ** 3),
        "corpus_vectors": int(index.ntotal),
        "training_seconds": training_seconds,
        "add_seconds": add_seconds,
        "write_seconds": write_seconds,
    }
    write_json_atomic(manifest_path, result)

    print(
        json.dumps(result, ensure_ascii=False, indent=2),
        flush=True,
    )

    del index
    del quantizer
    gc.collect()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从完整 Embedding Artifact 构建 FAISS IVFPQ serving index"
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        action="append",
        required=True,
        help="可重复传入 sentence / clause Embedding Artifact",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="每个 Artifact 的 index 子目录都会创建在这里",
    )
    parser.add_argument("--nlist", type=int, default=DEFAULT_NLIST)
    parser.add_argument("--pq-m", type=int, default=DEFAULT_PQ_M)
    parser.add_argument("--pq-bits", type=int, default=DEFAULT_PQ_BITS)
    parser.add_argument("--nprobe", type=int, default=DEFAULT_NPROBE)
    parser.add_argument(
        "--training-vectors",
        type=int,
        default=DEFAULT_TRAINING_VECTORS,
    )
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()

    results = []
    for artifact_dir in args.artifact_dir:
        output_dir = args.output_root / index_dir_name(
            artifact_dir,
            nlist=args.nlist,
            pq_m=args.pq_m,
            pq_bits=args.pq_bits,
        )
        results.append(
            build_full_index(
                artifact_dir,
                output_dir=output_dir,
                nlist=args.nlist,
                pq_m=args.pq_m,
                pq_bits=args.pq_bits,
                nprobe=args.nprobe,
                training_vectors=args.training_vectors,
                threads=args.threads,
            )
        )

    print(
        json.dumps(
            {
                "status": "complete",
                "indexes": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
