"""为 Werneror 的 clause Chunk 构建可断点续跑的 BERT-CCPoem Embedding。

这是 Retrieval Eval 的实验性专用领域模型对照方案，遵循官方
BERT-CCPoem 池化方式：对正文 Token 的隐藏状态做均值池化，
排除 [CLS]、[SEP] 和 Padding。

Poeticus 不内置该模型。需从 THUNLP-AIPoet 官方项目
下载 BERT-CCPoem v1.0，再通过 --model-path 指向本地模型目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from pydantic import ConfigDict, TypeAdapter, with_config

from backend.data_paths import RETRIEVAL_CORPUS_ROOT, RETRIEVAL_ROOT

from scripts.corpus.qwen_embedding_build import (
    EmbeddingManifest,
    RunSignature,
    assert_compatible_manifest,
    iter_chunks,
    save_shard_atomic,
    sha256_file,
    utc_now,
    validate_completed_shards,
    write_json_atomic,
)

MODEL_NAME = "THUNLP-AIPoet/BERT-CCPoem-v1.0"
CHUNK_POLICY = "clause"
DIMENSION = 512
DTYPE = "float16"
DEFAULT_INPUT = RETRIEVAL_CORPUS_ROOT / "werneror_chunks_clause.jsonl"
DEFAULT_OUTPUT_DIR = RETRIEVAL_ROOT / "embeddings/bert_ccpoem_clause_512"
DEFAULT_BATCH_SIZE = 512
DEFAULT_SHARD_SIZE = 10_000
DEFAULT_EXPECTED_CHUNKS = 9_425_173
MANIFEST_VERSION = 1


class BertRunSignature(RunSignature):
    pooling: str


@with_config(ConfigDict(extra="allow"))
class BertEmbeddingManifest(EmbeddingManifest):
    pooling: str
    acknowledgement: str


_BERT_MANIFEST_ADAPTER = TypeAdapter(BertEmbeddingManifest)



def fingerprint_model_dir(model_dir: Path) -> str:
    candidates = [
        model_dir / "config.json",
        model_dir / "vocab.txt",
        model_dir / "tokenizer_config.json",
        model_dir / "special_tokens_map.json",
        model_dir / "pytorch_model.bin",
        model_dir / "model.safetensors",
    ]
    files = [path for path in candidates if path.is_file()]
    if not any(
        path.name in {"pytorch_model.bin", "model.safetensors"}
        for path in files
    ):
        raise ValueError(f"BERT-CCPoem 模型目录缺少权重文件：{model_dir}")

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


def run_signature(
    *,
    input_sha256: str,
    model_fingerprint: str,
    shard_size: int,
    expected_chunks: int,
) -> BertRunSignature:
    return {
        "manifest_version": MANIFEST_VERSION,
        "model": MODEL_NAME,
        "model_fingerprint": model_fingerprint,
        "input_sha256": input_sha256,
        "chunk_policy": CHUNK_POLICY,
        "embedding_dimension": DIMENSION,
        "dtype": DTYPE,
        "normalized": True,
        "pooling": "mean_content_tokens_excluding_special",
        "shard_size": shard_size,
        "expected_chunks": expected_chunks,
    }


def encode_batch(texts, tokenizer, model, device, torch):
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        return_tensors="pt",
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}

    with torch.inference_mode():
        hidden = model(**encoded).last_hidden_state

    content_mask = encoded["attention_mask"].bool().clone()
    content_mask[:, 0] = False
    lengths = encoded["attention_mask"].sum(dim=1)
    row_ids = torch.arange(content_mask.shape[0], device=device)
    content_mask[row_ids, lengths - 1] = False

    counts = content_mask.sum(dim=1)
    if torch.any(counts == 0):
        raise ValueError("BERT-CCPoem 遇到没有正文 token 的 Chunk")

    vectors = (
        hidden * content_mask.unsqueeze(-1)
    ).sum(dim=1) / counts.unsqueeze(-1)
    vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
    return vectors.cpu().numpy()


def build_embeddings(
    *,
    input_path: Path,
    output_dir: Path,
    model_path: Path,
    expected_chunks: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    shard_size: int = DEFAULT_SHARD_SIZE,
    device: str | None = None,
) -> BertEmbeddingManifest:
    if not input_path.is_file():
        raise ValueError(f"Chunk JSONL 不存在：{input_path}")
    if not model_path.is_dir():
        raise ValueError(f"BERT-CCPoem 模型目录不存在：{model_path}")
    if expected_chunks <= 0 or batch_size <= 0 or shard_size <= 0:
        raise ValueError("expected-chunks / batch-size / shard-size 必须为正整数")

    try:
        import numpy as np
        import torch
        from transformers import AutoModel, BertModel, BertTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "BERT-CCPoem 构建需要 torch / transformers；"
            "请安装 requirements-retrieval.txt"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"

    print("计算语料 SHA256……", flush=True)
    input_sha256 = sha256_file(input_path)
    print("计算 BERT-CCPoem fingerprint……", flush=True)
    model_fingerprint = fingerprint_model_dir(model_path)

    signature = run_signature(
        input_sha256=input_sha256,
        model_fingerprint=model_fingerprint,
        shard_size=shard_size,
        expected_chunks=expected_chunks,
    )

    if manifest_path.is_file():
        manifest = _BERT_MANIFEST_ADAPTER.validate_python(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        assert_compatible_manifest(manifest, signature)
    else:
        leftovers = list(output_dir.iterdir())
        if leftovers:
            raise ValueError(
                f"输出目录已有文件但没有 manifest：{output_dir}；"
                "请换新目录，避免混入旧结果"
            )
        manifest: BertEmbeddingManifest = {
            **signature,
            "status": "running",
            "model_source": str(model_path),
            "input": str(input_path),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "completed_chunks": 0,
            "completed_shards": [],
            "acknowledgement": (
                "BERT-CCPoem, developed by Research Center for Natural "
                "Language Processing, Computational Humanities and Social "
                "Sciences, Tsinghua University."
            ),
        }
        write_json_atomic(manifest_path, manifest)

    resume_index = validate_completed_shards(manifest, output_dir, np)
    if manifest.get("status") == "complete":
        print(f"Embedding 已完整生成：{expected_chunks:,} 条。")
        return manifest

    selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = BertTokenizer.from_pretrained(
        str(model_path), local_files_only=True
    )
    model = AutoModel.from_pretrained(
        str(model_path), local_files_only=True
    )
    if not isinstance(model, BertModel):
        raise ValueError("BERT-CCPoem 模型配置必须对应 BertModel")
    torch.nn.Module.to(model, device=torch.device(selected_device))
    model.eval()

    if model.config.hidden_size != DIMENSION:
        raise ValueError(
            f"BERT-CCPoem hidden_size={model.config.hidden_size}，预期 {DIMENSION}"
        )

    print(
        json.dumps(
            {
                "input": str(input_path),
                "model": MODEL_NAME,
                "model_fingerprint": model_fingerprint,
                "device": selected_device,
                "dimension": DIMENSION,
                "pooling": signature["pooling"],
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

    total_shards = math.ceil(expected_chunks / shard_size)
    shard_index = resume_index // shard_size
    shard_records: list[dict[str, object]] = []
    shard_start = resume_index
    seen_chunks = 0

    def flush_shard(records: list[dict[str, object]], start: int, index: int) -> int:
        end = start + len(records)
        print(
            f"[{index + 1}/{total_shards}] BERT-CCPoem "
            f"{start:,}..{end - 1:,} ({end / expected_chunks:.1%})",
            flush=True,
        )

        parts = []
        for batch_start in range(0, len(records), batch_size):
            batch = records[batch_start:batch_start + batch_size]
            texts = [record["text"] for record in batch]
            if not all(isinstance(text, str) for text in texts):
                raise ValueError("Chunk text 必须是字符串")
            parts.append(
                encode_batch(
                    [text for text in texts if isinstance(text, str)],
                    tokenizer,
                    model,
                    selected_device,
                    torch,
                )
            )

        vectors = np.concatenate(parts, axis=0)
        if vectors.shape != (len(records), DIMENSION):
            raise RuntimeError(
                f"Embedding shape={vectors.shape}，"
                f"预期 {(len(records), DIMENSION)}"
            )
        vectors = vectors.astype(np.float16, copy=False)

        filename = f"shard_{index:05d}.npy"
        shard_path = output_dir / filename
        save_shard_atomic(shard_path, vectors, np)

        manifest["completed_shards"].append(
            {
                "index": index,
                "start": start,
                "end": end,
                "file": filename,
                "sha256": sha256_file(shard_path),
                "bytes": shard_path.stat().st_size,
            }
        )
        manifest["completed_chunks"] = end
        manifest["updated_at"] = utc_now()
        write_json_atomic(manifest_path, manifest)
        return end

    for global_index, record in iter_chunks(
        input_path, chunk_policy=CHUNK_POLICY
    ):
        seen_chunks = global_index + 1
        if seen_chunks > expected_chunks:
            raise ValueError(
                f"Chunk JSONL 超过 expected-chunks={expected_chunks:,}"
            )
        if global_index < resume_index:
            continue
        if not shard_records:
            shard_start = global_index
        shard_records.append(record)
        if len(shard_records) >= shard_size:
            flush_shard(shard_records, shard_start, shard_index)
            shard_records = []
            shard_index += 1

    if shard_records:
        flush_shard(shard_records, shard_start, shard_index)

    if seen_chunks != expected_chunks:
        raise ValueError(
            f"Chunk JSONL 实际 {seen_chunks:,} 条，"
            f"与 expected-chunks={expected_chunks:,} 不一致"
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
        f"{manifest['total_bytes'] / 1024**3:.2f} GiB",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="全量生成 Werneror clause Chunk 的 BERT-CCPoem Embedding"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument(
        "--expected-chunks", type=int, default=DEFAULT_EXPECTED_CHUNKS
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    parser.add_argument("--device", help="可选：cuda / cpu")
    args = parser.parse_args()

    build_embeddings(
        input_path=args.input,
        output_dir=args.output_dir,
        model_path=args.model_path.expanduser().resolve(),
        expected_chunks=args.expected_chunks,
        batch_size=args.batch_size,
        shard_size=args.shard_size,
        device=args.device,
    )


if __name__ == "__main__":
    main()
