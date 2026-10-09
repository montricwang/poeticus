"""校验已完成的 Embedding Artifact 时不导入实验 CLI。"""
from __future__ import annotations

import json

import pytest

from backend.retrieval.embedding_artifact import (
    BERT_CCPOEM_MODEL,
    QWEN_MODEL,
    ExactManifest,
    load_artifact_manifest,
)


def write_artifact(tmp_path, *, changes=None):
    root = tmp_path / "embedding"
    root.mkdir()
    for name in ("first.npy", "second.npy"):
        (root / name).write_bytes(b"synthetic-shard")
    manifest = {
        "status": "complete",
        "model": QWEN_MODEL,
        "model_fingerprint": "a1b2c3d4",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "completed_chunks": 5,
        "completed_shards": [
            {"start": 0, "end": 2, "file": "first.npy"},
            {"start": 2, "end": 5, "file": "second.npy"},
        ],
        "input_sha256": "corpus-sha",
        "future_field": {"kept": True},
    }
    manifest.update(changes or {})
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize(
    ("model", "policy"),
    [(QWEN_MODEL, "sentence"), (QWEN_MODEL, "clause"), (BERT_CCPOEM_MODEL, "clause")],
)
def test_loader_keeps_models_policies_and_extra_fields(tmp_path, model, policy):
    root = write_artifact(
        tmp_path, changes={"model": model, "chunk_policy": policy}
    )
    result = load_artifact_manifest(root)
    assert result["model"] == model
    assert result["chunk_policy"] == policy
    assert result["completed_chunks"] == 5
    assert result.get("input_sha256") == "corpus-sha"
    assert dict(result)["future_field"] == {"kept": True}  # extra="allow"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"status": "running"}, "尚未完成"),
        ({"model": "unknown"}, "Embedding model"),
        ({"chunk_policy": "paragraph"}, "chunk_policy"),
        ({"embedding_dimension": 0}, "embedding_dimension"),
        ({"completed_chunks": 0}, "completed_chunks"),
        ({"model_fingerprint": ""}, "model_fingerprint"),
        ({"completed_shards": []}, "completed_shards"),
        (
            {"completed_shards": [
                {"start": 0, "end": 2, "file": "first.npy"},
                {"start": 3, "end": 5, "file": "second.npy"},
            ]},
            "连续区间",
        ),
        (
            {"completed_shards": [
                {"start": 0, "end": 2, "file": "first.npy"},
                {"start": 2, "end": 4, "file": "second.npy"},
            ]},
            "范围不一致",
        ),
        (
            {"completed_shards": [
                {"start": 0, "end": 2, "file": "first.npy"},
                {"start": 2, "end": 5, "file": "missing.npy"},
            ]},
            "Embedding shard 不存在",
        ),
    ],
)
def test_loader_rejects_inconsistent_artifacts(tmp_path, changes, message):
    root = write_artifact(tmp_path, changes=changes)
    with pytest.raises(ValueError, match=message):
        load_artifact_manifest(root)


def test_loader_rejects_missing_manifest(tmp_path):
    with pytest.raises(ValueError, match="Embedding manifest 不存在"):
        load_artifact_manifest(tmp_path)


def test_offline_builder_and_experiment_reuse_same_loader():
    from scripts.retrieval import artifact_search, exact_search, faiss_full_index

    assert artifact_search.load_artifact_manifest is load_artifact_manifest
    assert faiss_full_index.load_artifact_manifest is load_artifact_manifest
    assert exact_search.ExactManifest is ExactManifest
