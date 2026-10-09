"""全量 FAISS 构建器与独立 Spike 共用同一抽样器。"""
import numpy as np
import pytest

from scripts.retrieval.faiss_full_index import load_sampled_vectors, sample_global_rows
from scripts.retrieval.vector_sampling import (
    load_sampled_vectors as shared_load_sampled_vectors,
    sample_global_rows as shared_sample_global_rows,
)


def test_full_index_uses_shared_sampler():
    assert load_sampled_vectors is shared_load_sampled_vectors
    assert sample_global_rows is shared_sample_global_rows


def test_sample_global_rows_are_deterministic_and_bounded():
    assert sample_global_rows(6, 3).tolist() == [0, 2, 5]
    assert sample_global_rows(3, 10).tolist() == [0, 1, 2]
    with pytest.raises(ValueError):
        sample_global_rows(0, 10)


def test_sampled_vectors_read_across_shard_boundaries(tmp_path):
    np.save(tmp_path / "a.npy", np.array([[3, 4], [0, 5]], dtype=np.float16))
    np.save(tmp_path / "b.npy", np.array([[5, 0], [4, 3]], dtype=np.float16))
    manifest = {
        "embedding_dimension": 2,
        "completed_shards": [
            {"file": "a.npy", "start": 0, "end": 2},
            {"file": "b.npy", "start": 2, "end": 4},
        ],
    }
    vectors = load_sampled_vectors(tmp_path, manifest, np.array([0, 3, 2]))
    assert vectors.dtype == np.float32
    assert np.allclose(vectors, [[0.6, 0.8], [0.8, 0.6], [1, 0]])


def test_missing_sampled_row_is_an_error(tmp_path):
    np.save(tmp_path / "a.npy", np.array([[3, 4]], dtype=np.float16))
    manifest = {
        "embedding_dimension": 2,
        "completed_shards": [{"file": "a.npy", "start": 0, "end": 1}],
    }
    with pytest.raises(ValueError, match="缺少采样 row"):
        load_sampled_vectors(tmp_path, manifest, np.array([0, 1]))
