"""Bundle 路径解析供多个工具共用，本身不会启动服务器。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.retrieval.serving_paths import default_paths
from scripts.retrieval.benchmark_serving import default_paths as benchmark_paths
from scripts.retrieval.inspect_serving_bundle import default_paths as inspect_paths
from scripts.retrieval.run_serving import default_paths as launcher_paths


def write_sentence_manifest(data_root: Path, value: object) -> None:
    parent = data_root / "embeddings/qwen3_0.6b_sentence_1024"
    parent.mkdir(parents=True)
    (parent / "manifest.json").write_text(
        json.dumps({"model_fingerprint": value}),
        encoding="utf-8",
    )


def test_all_serving_tools_share_one_layout_resolver(tmp_path: Path) -> None:
    data_root = tmp_path / "data" / "retrieval"
    model_root = tmp_path / "data" / "models"
    write_sentence_manifest(data_root, "abcdef1234567890")
    expected = default_paths(data_root, model_root)

    assert launcher_paths is default_paths
    assert benchmark_paths is default_paths
    assert inspect_paths is default_paths
    assert expected.sentence_embedding_dir == (
        data_root / "embeddings/qwen3_0.6b_sentence_1024"
    )
    assert expected.sentence_faiss_dir == (
        data_root / "faiss/qwen3_0.6b_sentence_1024_ivfpq_nlist512_m256_b8"
    )
    assert expected.clause_embedding_dir == (
        data_root / "embeddings/qwen3_0.6b_clause_1024"
    )
    assert expected.clause_faiss_dir == (
        data_root / "faiss/qwen3_0.6b_clause_1024_ivfpq_nlist512_m256_b8"
    )
    assert expected.bm25_sentence_dir == data_root / "lexical/bm25_sentence_2_3"
    assert expected.metadata_db == data_root / "serving/retrieval_metadata.sqlite3"
    assert expected.model_path == model_root / "Qwen3-Embedding-0.6B-abcdef123456"
    assert launcher_paths(data_root, model_root) == expected


@pytest.mark.parametrize("fingerprint", ["", None, 123])
def test_resolver_rejects_missing_model_fingerprint(
    tmp_path: Path,
    fingerprint: object,
) -> None:
    data_root = tmp_path / "retrieval"
    write_sentence_manifest(data_root, fingerprint)
    with pytest.raises(ValueError, match="model_fingerprint"):
        default_paths(data_root, tmp_path / "models")
