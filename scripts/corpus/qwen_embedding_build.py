"""为 Werneror sentence Chunk 构建可断点续跑的 Qwen Embedding。

流程：

    sentence Chunk JSONL
      → Qwen3-Embedding-0.6B
      → 归一化的 512 维向量
      → float16 NumPy 分片与 Manifest

这是离线 Corpus 构建步骤，不创建向量数据库或 ANN 索引。
完成的分片可以供后续 pgvector / FAISS 导入复用。

Manifest 将运行结果与输入语料 Hash、模型指纹和 Embedding 参数绑定；
中断后仅在配置兼容时自动续跑。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_ROOT
from typing import Iterator, Mapping, NotRequired, TypedDict

from pydantic import ConfigDict, TypeAdapter, with_config

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_INPUT = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_sentence.jsonl"
DEFAULT_OUTPUT_DIR = RETRIEVAL_ROOT / "embeddings/qwen3_0.6b_sentence_512"
DEFAULT_DIMENSION = 512
DEFAULT_BATCH_SIZE = 64
DEFAULT_SHARD_SIZE = 10_000
DEFAULT_EXPECTED_CHUNKS = 4_822_054
DTYPE = "float16"
CHUNK_POLICY = "sentence"
MANIFEST_VERSION = 1


class RunSignature(TypedDict):
    manifest_version: int
    model: str
    model_fingerprint: str
    input_sha256: str
    chunk_policy: str
    embedding_dimension: int
    dtype: str
    normalized: bool
    shard_size: int
    expected_chunks: int


class CompletedShard(TypedDict):
    index: int
    start: int
    end: int
    file: str
    sha256: str
    bytes: int


@with_config(ConfigDict(extra="allow"))
class EmbeddingManifest(RunSignature):
    """恢复运行状态，同时保留尚不认识的元数据字段以兼容后续版本。"""

    status: str
    model_source: str
    input: str
    created_at: str
    updated_at: str
    completed_chunks: int
    completed_shards: list[CompletedShard]
    completed_at: NotRequired[str]
    total_shards: NotRequired[int]
    total_bytes: NotRequired[int]


_MANIFEST_ADAPTER = TypeAdapter(EmbeddingManifest)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def fingerprint_model_dir(model_dir: Path) -> str:
    """为实际决定 Embedding 结果的本地模型文件计算指纹。"""
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


def iter_chunks(
    path: Path,
    chunk_policy: str = CHUNK_POLICY,
) -> Iterator[tuple[int, dict[str, object]]]:
    """依次返回从零开始的语料行号及已校验的 Chunk 记录。"""
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
            if record["policy"] != chunk_policy:
                raise ValueError(
                    f"Chunk JSONL 第 {line_no} 行 policy={record['policy']!r}，"
                    f"预期 {chunk_policy!r}"
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
    chunk_policy: str = CHUNK_POLICY,
) -> RunSignature:
    return {
        "manifest_version": MANIFEST_VERSION,
        "model": MODEL_NAME,
        "model_fingerprint": model_fingerprint,
        "input_sha256": input_sha256,
        "chunk_policy": chunk_policy,
        "embedding_dimension": dimension,
        "dtype": DTYPE,
        "normalized": True,
        "shard_size": shard_size,
        "expected_chunks": expected_chunks,
    }


def assert_compatible_manifest(
    manifest: Mapping[str, object], signature: Mapping[str, object]
) -> None:
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


def write_json_atomic(path: Path, payload: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def validate_completed_shards(manifest: EmbeddingManifest, output_dir: Path, np) -> int:
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
    chunk_policy: str = CHUNK_POLICY,
) -> EmbeddingManifest:
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
        chunk_policy=chunk_policy,
    )

    if manifest_path.is_file():
        manifest = _MANIFEST_ADAPTER.validate_python(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
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
        manifest: EmbeddingManifest = {
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
                "chunk_policy": chunk_policy,
                "resume_from": resume_index,
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    print("加载本地 Qwen Embedding 模型……", flush=True)
    model = SentenceTransformer(
        str(model_path), local_files_only=True, device=device
    )
    print(f"device={model.device}", flush=True)

    total_shards = math.ceil(expected_chunks / shard_size)
    shard_index = resume_index // shard_size
    batch_records: list[dict[str, object]] = []
    batch_start = resume_index
    seen_chunks = 0

    def flush_shard(records: list[dict[str, object]], start: int, index: int) -> int:
        texts: list[str] = []
        for record in records:
            value = record["text"]
            if not isinstance(value, str):
                raise ValueError("Embedding Chunk 文本必须是字符串")
            texts.append(value)
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

    for global_index, record in iter_chunks(
        input_path, chunk_policy=chunk_policy
    ):
        seen_chunks = global_index + 1
        if seen_chunks > expected_chunks:
            raise ValueError(
                f"Chunk JSONL 超过 expected-chunks={expected_chunks:,}；"
                "停止生成，避免把异常输入写入新 shard"
            )
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
        "--chunk-policy",
        default=CHUNK_POLICY,
        choices=("sentence", "clause"),
        help="输入 Chunk JSONL 的 policy",
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
        chunk_policy=args.chunk_policy,
    )


if __name__ == "__main__":
    main()
