import json

import pytest

from scripts.retrieval.artifact_search import (
    BERT_CCPOEM_MODEL,
    QWEN_MODEL,
    load_artifact_manifest,
    resolve_chunk_path,
    resolve_query_model_path,
)
from scripts.retrieval.compare_artifacts import summarize_result


def _write_artifact(tmp_path, *, model=QWEN_MODEL, policy="sentence"):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "shard_00000.npy").write_bytes(b"placeholder")
    manifest = {
        "status": "complete",
        "model": model,
        "model_fingerprint": "abcdef1234567890",
        "chunk_policy": policy,
        "embedding_dimension": 1024 if model == QWEN_MODEL else 512,
        "completed_chunks": 2,
        "completed_shards": [
            {"start": 0, "end": 2, "file": "shard_00000.npy"}
        ],
    }
    (artifact / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return artifact


@pytest.mark.parametrize(
    ("model", "policy"),
    [
        (QWEN_MODEL, "sentence"),
        (QWEN_MODEL, "clause"),
        (BERT_CCPOEM_MODEL, "clause"),
    ],
)
def test_load_artifact_manifest_accepts_comparison_artifacts(
    tmp_path, model, policy
):
    artifact = _write_artifact(tmp_path, model=model, policy=policy)

    manifest = load_artifact_manifest(artifact)

    assert manifest["model"] == model
    assert manifest["chunk_policy"] == policy


def test_resolve_chunk_path_follows_manifest_policy(monkeypatch, tmp_path):
    from scripts.retrieval import artifact_search

    sentence = tmp_path / "sentence.jsonl"
    clause = tmp_path / "clause.jsonl"
    monkeypatch.setattr(
        artifact_search,
        "CHUNK_PATHS",
        {"sentence": sentence, "clause": clause},
    )

    assert resolve_chunk_path({"chunk_policy": "sentence"}, None) == sentence.resolve()
    assert resolve_chunk_path({"chunk_policy": "clause"}, None) == clause.resolve()


def test_resolve_query_model_path_uses_model_specific_default(monkeypatch, tmp_path):
    from scripts.retrieval import artifact_search

    monkeypatch.setattr(artifact_search, "DEFAULT_MODEL_ROOT", tmp_path)

    qwen = resolve_query_model_path(
        {
            "model": QWEN_MODEL,
            "model_fingerprint": "abcdef1234567890",
        },
        None,
    )
    bert = resolve_query_model_path(
        {
            "model": BERT_CCPOEM_MODEL,
            "model_fingerprint": "ignored",
        },
        None,
    )

    assert qwen == (tmp_path / "Qwen3-Embedding-0.6B-abcdef123456").resolve()
    assert bert == (tmp_path / "BERT_CCPoem_v1").resolve()


def test_summarize_result_uses_best_probe_rank():
    result = {
        "model": QWEN_MODEL,
        "chunk_policy": "clause",
        "dimension": 1024,
        "corpus_chunks": 100,
        "probes": [
            {"rank": 7, "cosine": 0.7, "chunk": {"text": "甲"}},
            {"rank": 2, "cosine": 0.8, "chunk": {"text": "乙"}},
        ],
    }

    summary = summarize_result("qwen_clause_1024", result)

    assert summary["best_probe_rank"] == 2
    assert summary["best_probe_cosine"] == 0.8
    assert summary["best_probe_text"] == "乙"
    assert summary["probe_matches"] == 2
