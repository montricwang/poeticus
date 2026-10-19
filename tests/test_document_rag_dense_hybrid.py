"""Document RAG Dense/RRF 离线 Runner 的无模型单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.experiments.document_rag_dense_hybrid import (
    cache_spec,
    fuse_rrf,
    read_or_create_spec,
    section_text,
    summary,
    valid_batch,
)


def test_rrf_uses_rank_not_raw_score_and_merges_duplicate() -> None:
    first = [("a", 200.0), ("b", 0.001)]
    second = [("b", -4.0), ("c", 0.9)]
    fused = fuse_rrf(first, second, 3)
    assert [x[0] for x in fused] == ["b", "a", "c"]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_tie_is_stable() -> None:
    result = fuse_rrf([("c", 1.0)], [("a", 1.0)], 2)
    assert [r[0] for r in result] == ["a", "c"]


def test_section_text_uses_title_and_body_only() -> None:
    assert section_text({"title": "正文题", "text": "这段正文", "doc": "文献甲"}) == "正文题 这段正文"


def test_cache_disallows_stale_corpus(tmp_path: Path) -> None:
    directory = tmp_path / "vectors"
    read_or_create_spec(directory, {"corpus_sha256": "first"})
    with pytest.raises(ValueError, match="缓存配置"):
        read_or_create_spec(directory, {"corpus_sha256": "second"})


def test_batch_shape_and_finite_values(tmp_path: Path) -> None:
    path = tmp_path / "batch_0000.npy"
    np.save(path, np.eye(3, dtype=np.float32))
    assert valid_batch(path, 3, 3)
    with pytest.raises(ValueError, match="损坏"):
        valid_batch(path, 3, 2)
    np.save(path, np.array([[np.nan]], dtype=np.float32))
    with pytest.raises(ValueError, match="损坏"):
        valid_batch(path, 1, 1)


def test_spec_tracks_model_prompts(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text("[]", encoding="utf-8")
    model = tmp_path / "model"
    model.mkdir()
    (model / "config_sentence_transformers.json").write_text(
        json.dumps({"prompts": {"query": "Instruct: Search\\nQuery: ", "document": ""}}),
        encoding="utf-8",
    )
    result = cache_spec(corpus, model, 20, 4, 512)
    assert result["sections"] == 20
    assert result["model_prompt_config_sha256"]
    assert result["query_prompt"].startswith("Instruct:")


def test_summary_stays_separate_from_other_methods() -> None:
    result = summary([{
        "hit_at_k": True, "all_gold_at_k": False, "recall_at_k": 0.5, "reciprocal_rank": 0.5,
    }, {
        "hit_at_k": False, "all_gold_at_k": False, "recall_at_k": 0.0, "reciprocal_rank": 0.0,
    }])
    assert result["hit_at_5"] == 0.5
    assert result["all_gold_at_5"] == 0.0
    assert result["mean_recall_at_5"] == 0.25
