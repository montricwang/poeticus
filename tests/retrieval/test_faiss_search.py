import json

import pytest

from scripts.retrieval.faiss_search import (
    load_index_manifest,
    probe_ranks,
)


def embedding_manifest():
    return {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "model_fingerprint": "abc123",
        "input_sha256": "deadbeef",
        "chunk_policy": "sentence",
        "embedding_dimension": 1024,
        "dtype": "float16",
        "normalized": True,
        "completed_chunks": 100,
    }


def index_manifest():
    return {
        "manifest_version": 1,
        "engine": "faiss_IndexIVFPQ",
        "source_embedding": embedding_manifest(),
        "nlist": 512,
        "pq_m": 256,
        "pq_bits": 8,
        "nprobe": 64,
        "training_vectors": 50,
        "row_id_contract": (
            "faiss_id == embedding_global_row == chunk_jsonl_logical_row"
        ),
        "status": "complete",
        "index_file": "index.faiss",
        "index_bytes": 4,
        "index_gib": 4 / (1024 ** 3),
        "corpus_vectors": 100,
    }


def test_load_index_manifest_accepts_matching_artifact(tmp_path):
    (tmp_path / "index.faiss").write_bytes(b"FAKE")
    (tmp_path / "manifest.json").write_text(
        json.dumps(index_manifest()),
        encoding="utf-8",
    )

    loaded = load_index_manifest(
        tmp_path,
        embedding_manifest=embedding_manifest(),
    )

    assert loaded["pq_m"] == 256
    assert loaded["corpus_vectors"] == 100


def test_load_index_manifest_rejects_embedding_mismatch(tmp_path):
    (tmp_path / "index.faiss").write_bytes(b"FAKE")
    manifest = index_manifest()
    manifest["source_embedding"]["input_sha256"] = "other"
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="不匹配"):
        load_index_manifest(
            tmp_path,
            embedding_manifest=embedding_manifest(),
        )


def test_probe_ranks_reports_hit_and_miss():
    assert probe_ranks([9, 3, 7], {3, 4}) == [
        {"global_row": 3, "retrieved_rank": 2},
        {"global_row": 4, "retrieved_rank": None},
    ]
