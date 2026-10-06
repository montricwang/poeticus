"""Build resumable Qwen embeddings for Werneror sentence chunks.

Pipeline:

    sentence Chunk JSONL
        -> Qwen3-Embedding-0.6B
        -> normalized 512-d embeddings
        -> float16 NumPy shards + manifest

This is an offline corpus build step. It does not create a vector database or
an ANN index. Completed shards are reusable artifacts for later pgvector /
FAISS import.

The manifest binds a run to the exact input corpus hash, model fingerprint and
embedding parameters. A compatible interrupted run resumes automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_INPUT = Path("data/output/retrieval/werneror_chunks_sentence.jsonl")
DEFAULT_OUTPUT_DIR = Path(
    "data/output/retrieval/embeddings/qwen3_0.6b_sentence_512"
)
DEFAULT_DIMENSION = 512
DEFAULT_BATCH_SIZE = 64
DEFAULT_SHARD_SIZE = 10_000
DEFAULT_EXPECTED_CHUNKS = 4_822_054
DTYPE = "float16"
CHUNK_POLICY = "sentence"
MANIFEST_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def fingerprint_model_dir(model_dir: Path) -> str:
    """Fingerprint local model files that materially define embeddings."""
    candidates = [
        model_dir / "config.json",
        model_dir / "modules.json",
        model_dir / "sentence_bert_config.json",
        model_dir / "config_sentence_transformers.json",
        *sorted(model_dir.glob("*.safetensors")),
    ]
    files = [path for path in candidates if path.is_file()]
    if not any(path.suffix == ".safetensors" for path in files):
        raise ValueError(f"本地模型目录没有 safetensors 权重：{model_dir}")

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(model_dir).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
    return digest.hexdigest()


def iter_chunks(path: Path) -> Iterator[tuple[int, dict]]:
    """Yield zero-based corpus row index plus validated Chunk record."""
    index = 0
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Chunk JSONL 第 {line_no} 行无法解析") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Chunk JSONL 第 {line_no} 行不是对象")
            required = {"chunk_id", "policy", "text"}
            if not required <= set(record):
                raise ValueError(f"Chunk JSONL 第 {line_no} 行缺少必要字段")
            if record["policy"] != CHUNK_POLICY:
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行 policy={record['policy']!r}，"
                    f"预期 {CHUNK_POLICY!r}"
                )
            if not isinstance(record["text"], str) or not record["text"]:
                raise ValueError(f"Chunk JSONL 第 {line_no} 行 text 不是非空字符串")
            yield index, record
            index += 1


def run_signature(
    *,
    input_sha256: str,
    model_fingerprint: str,
    dimension: int,
    shard_size: int,
    expected_chunks: int,
) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "model": MODEL_NAME,
        "model_fingerprint": model_fingerprint,
        "input_sha256": input_sha256,
        "chunk_policy": CHUNK_POLICY,
        "embedding_dimension": dimension,
        "dtype": DTYPE,
        "normalized": True,
        "shard_size": shard_size,
        "expected_chunks": expected_chunks,
    }


def assert_compatible_manifest(manifest: dict, signature: dict) -> None:
    mismatches = []
    for key, expected in signature.items():
        actual = manifest.get(key)
        if actual != expected:
            mismatches.append(f"{key}: 已有={actual!r}, 本次={expected!r}")
    if mismatches:
        raise ValueError(
            "已有 Embedding manifest 与本次参数不兼容；"
            "请换一个 --output-dir，而不要混用旧 shard。\n"
            + "\n".join(mismatches)
        )


def write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def validate_completed_shards(manifest: dict, output_dir: Path, np) -> int:
    completed = manifest.get("completed_shards", [])
    expected_start = 0
    dimension = manifest["embedding_dimension"]

    for item in completed:
        start = item.get("start")
        end = item.get("end")
        filename = item.get("file")
        if start != expected_start or not isinstance(end, int) or end <= start:
            raise ValueError("manifest 中 completed_shards 不是连续区间")
        path = output_dir / filename
        if not path.is_file():
            raise ValueError(f"manifest 记录的 shard 不存在：{path}")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if array.shape != (end - start, dimension):
            raise ValueError(
                f"{path.name} shape={array.shape}，"
                f"预期 {(end - start, dimension)}"
            )
        if str(array.dtype) != DTYPE:
            raise ValueError(
                f"{path.name} dtype={array.dtype}，预期 {DTYPE}"
            )
        expected_start = end

    if manifest.get("completed_chunks", 0) != expected_start:
        raise ValueError(
            "manifest 的 completed_chunks 与 completed_shards 不一致"
        )
    return expected_start


def save_shard_atomic(path: Path, vectors, np) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        np.save(stream, vectors, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def build_embeddings(
    *,
    input_path: Path,
    output_dir: Path,
    model_path: Path,
    dimension: int,
    batch_size: int,
    shard_size: int,
    expected_chunks: int,
    device: str | None = None,
) -> dict:
    if not input_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{input_path}")
    if not model_path.is_dir():
        raise ValueError(f"本地模型目录不存在：{model_path}")
    if dimension <= 0 or batch_size <= 0 or shard_size <= 0:
        raise ValueError("dimension / batch-size / shard-size 必须为正整数")
    if expected_chunks <= 0:
        raise ValueError("expected-chunks 必须为正整数")

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 Retrieval 依赖，请先运行："
            "pip install -r requirements-retrieval.txt"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"

    print("计算语料 SHA256……", flush=True)
    input_sha256 = sha256_file(input_path)
    print("计算本地模型 fingerprint……", flush=True)
    model_fingerprint = fingerprint_model_dir(model_path)

    signature = run_signature(
        input_sha256=input_sha256,
        model_fingerprint=model_fingerprint,
        dimension=dimension,
        shard_size=shard_size,
        expected_chunks=expected_chunks,
    )

    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert_compatible_manifest(manifest, signature)
    else:
        leftovers = [
            path.name
            for path in output_dir.iterdir()
            if path.name != manifest_path.name
        ]
        if leftovers:
            raise ValueError(
                f"输出目录已有文件但没有 manifest：{output_dir}；"
                "请换新目录，避免混入旧结果"
            )
        manifest = {
            **signature,
            "status": "running",
            "model_source": str(model_path),
            "input": str(input_path),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "completed_chunks": 0,
            "completed_shards": [],
        }
        write_json_atomic(manifest_path, manifest)

    resume_index = validate_completed_shards(manifest, output_dir, np)
    if manifest.get("status") == "complete":
        if resume_index != expected_chunks:
            raise ValueError("manifest 标为 complete，但完成数量与 expected-chunks 不符")
        print(f"Embedding 已完整生成：{expected_chunks:,} 条。")
        return manifest

    print(
        json.dumps(
            {
                "input": str(input_path),
                "input_sha256": input_sha256,
                "model": MODEL_NAME,
                "model_source": str(model_path),
                "model_fingerprint": model_fingerprint,
                "dimension": dimension,
                "dtype": DTYPE,
                "normalized": True,
                "batch_size": batch_size,
                "shard_size": shard_size,
                "expected_chunks": expected_chunks,
                "resume_from": resume_index,
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    kwargs = {"local_files_only": True}
    if device:
        kwargs["device"] = device
    print("加载本地 Qwen Embedding 模型……", flush=True)
    model = SentenceTransformer(str(model_path), **kwargs)
    print(f"device={model.device}", flush=True)

    total_shards = math.ceil(expected_chunks / shard_size)
    shard_index = resume_index // shard_size
    batch_records: list[dict] = []
    batch_start = resume_index
    seen_chunks = 0

    def flush_shard(records: list[dict], start: int, index: int) -> int:
        texts = [record["text"] for record in records]
        end = start + len(texts)
        print(
            f"[{index + 1}/{total_shards}] Embedding "
            f"{start:,}..{end - 1:,} ({end / expected_chunks:.1%})",
            flush=True,
        )
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
            truncate_dim=dimension,
        )
        if vectors.shape != (len(texts), dimension):
            raise RuntimeError(
                f"Embedding shape={vectors.shape}，"
                f"预期 {(len(texts), dimension)}"
            )
        vectors = vectors.astype(np.float16, copy=False)

        filename = f"shard_{index:05d}.npy"
        shard_path = output_dir / filename
        save_shard_atomic(shard_path, vectors, np)
        shard_sha256 = sha256_file(shard_path)

        manifest["completed_shards"].append(
            {
                "index": index,
                "start": start,
                "end": end,
                "file": filename,
                "sha256": shard_sha256,
                "bytes": shard_path.stat().st_size,
            }
        )
        manifest["completed_chunks"] = end
        manifest["updated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        return end

    for global_index, record in iter_chunks(input_path):
        seen_chunks = global_index + 1
        if global_index < resume_index:
            continue
        if not batch_records:
            batch_start = global_index
        batch_records.append(record)
        if len(batch_records) >= shard_size:
            next_index = flush_shard(
                batch_records, batch_start, shard_index
            )
            batch_records = []
            shard_index += 1
            if next_index != manifest["completed_chunks"]:
                raise AssertionError("manifest 完成位置异常")

    if batch_records:
        flush_shard(batch_records, batch_start, shard_index)

    if seen_chunks != expected_chunks:
        raise ValueError(
            f"Chunk JSONL 实际 {seen_chunks:,} 条，"
            f"与 expected-chunks={expected_chunks:,} 不一致；"
            "manifest 保持 running，修正输入或参数后再处理"
        )
    if manifest["completed_chunks"] != expected_chunks:
        raise RuntimeError(
            f"最终只完成 {manifest['completed_chunks']:,} 条，"
            f"预期 {expected_chunks:,}"
        )

    manifest["status"] = "complete"
    manifest["completed_at"] = utc_now()
    manifest["updated_at"] = manifest["completed_at"]
    manifest["total_shards"] = len(manifest["completed_shards"])
    manifest["total_bytes"] = sum(
        item["bytes"] for item in manifest["completed_shards"]
    )
    write_json_atomic(manifest_path, manifest)
    print(
        f"完成：{expected_chunks:,} 条，"
        f"{len(manifest['completed_shards'])} 个 shard，"
        f"{manifest['total_bytes'] / 1024**3:.2f} GiB",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="全量生成 Werneror sentence Chunk 的 Qwen Embedding shards"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--model-path",
        type=Path,
        required=True,
        help="完整本地 Qwen3-Embedding-0.6B snapshot 目录",
    )
    parser.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    parser.add_argument(
        "--expected-chunks", type=int, default=DEFAULT_EXPECTED_CHUNKS
    )
    parser.add_argument(
        "--device",
        help="可选：显式指定 cpu / cuda / mps；默认交给 sentence-transformers",
    )
    args = parser.parse_args()

    build_embeddings(
        input_path=args.input,
        output_dir=args.output_dir,
        model_path=args.model_path.expanduser().resolve(),
        dimension=args.dimension,
        batch_size=args.batch_size,
        shard_size=args.shard_size,
        expected_chunks=args.expected_chunks,
        device=args.device,
    )


if __name__ == "__main__":
    main()
