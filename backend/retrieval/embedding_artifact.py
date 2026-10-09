"""Contracts for completed, sharded Retrieval Embedding artifacts.

This module owns the manifest schema and its on-disk consistency checks.
Neither FAISS builders nor diagnostic search scripts need to import one another
just to validate an Embedding artifact. It does not load model or vector data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, TypeAdapter, with_config


QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
BERT_CCPOEM_MODEL = "THUNLP-AIPoet/BERT-CCPoem-v1.0"
SUPPORTED_MODELS = frozenset({QWEN_MODEL, BERT_CCPOEM_MODEL})
SUPPORTED_CHUNK_POLICIES = frozenset({"sentence", "clause"})


class ExactShard(TypedDict):
    start: int
    end: int
    file: str


@with_config(ConfigDict(extra="allow"))
class ExactManifest(TypedDict):
    status: str
    model: str
    model_fingerprint: str
    embedding_dimension: int
    completed_chunks: int
    completed_shards: list[ExactShard]
    input_sha256: NotRequired[str]


@with_config(ConfigDict(extra="allow"))
class ArtifactManifest(ExactManifest):
    chunk_policy: Literal["sentence", "clause"]


_ARTIFACT_MANIFEST_ADAPTER = TypeAdapter(ArtifactManifest)


def load_artifact_manifest(artifact_dir: Path) -> ArtifactManifest:
    """Validate a completed Embedding artifact and contiguous shard layout."""
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Embedding manifest 不存在：{manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Embedding manifest 必须是对象")
    if manifest.get("status") != "complete":
        raise ValueError(
            f"Embedding Artifact 尚未完成：status={manifest.get('status')!r}"
        )

    model = manifest.get("model")
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"尚不支持该 Embedding model：{model!r}")

    policy = manifest.get("chunk_policy")
    if policy not in SUPPORTED_CHUNK_POLICIES:
        raise ValueError(f"尚不支持该 chunk_policy：{policy!r}")

    dimension = manifest.get("embedding_dimension")
    completed_chunks = manifest.get("completed_chunks")
    shards = manifest.get("completed_shards")
    fingerprint = manifest.get("model_fingerprint")

    if not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("manifest 缺少有效 embedding_dimension")
    if not isinstance(completed_chunks, int) or completed_chunks <= 0:
        raise ValueError("manifest 缺少有效 completed_chunks")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError("manifest 缺少有效 model_fingerprint")
    if not isinstance(shards, list) or not shards:
        raise ValueError("manifest 缺少 completed_shards")

    expected_start = 0
    for item in shards:
        if not isinstance(item, dict):
            raise ValueError("Embedding shard 必须是对象")
        start = item.get("start")
        end = item.get("end")
        filename = item.get("file")
        if (
            not isinstance(start, int)
            or start != expected_start
            or not isinstance(end, int)
            or end <= start
        ):
            raise ValueError("manifest 中 completed_shards 不是连续区间")
        if not isinstance(filename, str) or not filename:
            raise ValueError("manifest shard 缺少文件名")
        if not (artifact_dir / filename).is_file():
            raise ValueError(f"Embedding shard 不存在：{artifact_dir / filename}")
        expected_start = end

    if expected_start != completed_chunks:
        raise ValueError(
            "manifest 的 completed_chunks 与 completed_shards 范围不一致"
        )

    return _ARTIFACT_MANIFEST_ADAPTER.validate_python(manifest)
