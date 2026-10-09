import json

from pydantic import ValidationError

import pytest

from scripts.corpus.qwen_embedding_build import (
    assert_compatible_manifest,
    iter_chunks,
    run_signature,
    RunSignature,
    _MANIFEST_ADAPTER,
)


def _signature(
    *, input_sha256: str = "corpus-hash",
    model_fingerprint: str = "model-hash",
    dimension: int = 512,
    shard_size: int = 10_000,
    expected_chunks: int = 123,
    chunk_policy: str = "sentence",
) -> RunSignature:
    return run_signature(
        input_sha256=input_sha256,
        model_fingerprint=model_fingerprint,
        dimension=dimension,
        shard_size=shard_size,
        expected_chunks=expected_chunks,
        chunk_policy=chunk_policy,
    )


def test_iter_chunks_preserves_global_nonblank_row_index(tmp_path):
    path = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "c0", "policy": "sentence", "text": "甲。"},
        {"chunk_id": "c1", "policy": "sentence", "text": "乙。"},
    ]
    path.write_text(
        json.dumps(rows[0], ensure_ascii=False)
        + "\n\n"
        + json.dumps(rows[1], ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    actual = list(iter_chunks(path))

    assert [index for index, _ in actual] == [0, 1]
    assert [record["chunk_id"] for _, record in actual] == ["c0", "c1"]


def test_iter_chunks_accepts_requested_clause_policy(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        json.dumps(
            {"chunk_id": "c0", "policy": "clause", "text": "甲，"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    actual = list(iter_chunks(path, chunk_policy="clause"))

    assert actual[0][1]["policy"] == "clause"


def test_iter_chunks_rejects_wrong_policy(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        json.dumps(
            {"chunk_id": "c0", "policy": "clause", "text": "甲。"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="policy"):
        list(iter_chunks(path))


def test_compatible_manifest_accepts_same_build_signature():
    signature = _signature()
    manifest = {**signature, "status": "running", "completed_chunks": 0}

    assert_compatible_manifest(manifest, signature)


def test_compatible_manifest_rejects_dimension_change():
    signature = _signature()
    manifest = {
        **_signature(dimension=1024),
        "status": "running",
        "completed_chunks": 0,
    }

    with pytest.raises(ValueError, match="embedding_dimension"):
        assert_compatible_manifest(manifest, signature)


def test_compatible_manifest_rejects_corpus_change():
    signature = _signature()
    manifest = {**signature, "input_sha256": "other-corpus"}

    with pytest.raises(ValueError, match="input_sha256"):
        assert_compatible_manifest(manifest, signature)


def test_resumable_manifest_preserves_extra_metadata() -> None:
    raw = {
        **_signature(),
        "status": "running",
        "model_source": "/models/synthetic",
        "input": "/corpus/synthetic.jsonl",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "completed_chunks": 0,
        "completed_shards": [],
        "future_metadata": {"retain": True},
    }
    validated = _MANIFEST_ADAPTER.validate_python(raw)
    assert dict(validated).get("future_metadata") == {"retain": True}


def test_resumable_manifest_rejects_malformed_shard_bounds() -> None:
    raw = {
        **_signature(),
        "status": "running",
        "model_source": "/models/synthetic",
        "input": "/corpus/synthetic.jsonl",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "completed_chunks": 1,
        "completed_shards": [{"index": 0, "start": "invalid", "end": 1, "file": "0.npy", "sha256": "x", "bytes": 4}],
    }
    with pytest.raises(ValidationError):
        _MANIFEST_ADAPTER.validate_python(raw)
