import json

import pytest

from scripts.corpus.qwen_embedding_build import (
    assert_compatible_manifest,
    iter_chunks,
    run_signature,
)


def _signature(**overrides):
    values = {
        "input_sha256": "corpus-hash",
        "model_fingerprint": "model-hash",
        "dimension": 512,
        "shard_size": 10_000,
        "expected_chunks": 123,
    }
    values.update(overrides)
    return run_signature(**values)


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
