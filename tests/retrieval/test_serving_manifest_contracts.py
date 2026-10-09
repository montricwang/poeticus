"""不导入 FAISS 或加载模型，单独测试 Manifest 边界。"""

import json

import pytest

from backend.retrieval.serving_manifest import (
    _embedding_source_signature,
    _load_json,
    _required_positive_int,
)


def test_manifest_loader_preserves_valid_json_fields(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = {
        "status": "complete",
        "embedding_dimension": 1024,
        "completed_chunks": 3,
        "completed_shards": [{"file": "part-001.npy", "start": 0, "end": 3}],
        "normalized": True,
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert _load_json(path) == manifest


@pytest.mark.parametrize("payload", ["[]", "null", '"complete"', "{bad"])
def test_manifest_loader_rejects_non_object_or_malformed_json(tmp_path, payload):
    path = tmp_path / "manifest.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="manifest 无法解析"):
        _load_json(path)


def test_manifest_loader_reports_missing_file(tmp_path):
    with pytest.raises(ValueError, match="manifest 不存在"):
        _load_json(tmp_path / "missing.json")


@pytest.mark.parametrize("value", [None, True, 0, -1, "1024", 1.5])
def test_manifest_integer_field_rejects_wrong_types_and_values(value):
    with pytest.raises(ValueError, match="embedding_dimension"):
        _required_positive_int({"embedding_dimension": value}, "embedding_dimension")


def test_manifest_integer_field_accepts_positive_integer():
    assert _required_positive_int({"nprobe": 64}, "nprobe") == 64


def test_embedding_source_signature_preserves_build_contract():
    manifest = {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "abc123",
        "input_sha256": "deadbeef",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "dtype": "float16",
        "normalized": True,
        "completed_chunks": 3,
        "status": "complete",
    }

    manifest: dict[str, object] = manifest
    signature = _embedding_source_signature(manifest)
    assert signature == {key: value for key, value in manifest.items() if key != "status"}


def test_embedding_source_signature_rejects_missing_required_key():
    with pytest.raises(ValueError, match="embedding_dimension"):
        _embedding_source_signature({"model": "Qwen/Qwen3-Embedding-0.6B"})
