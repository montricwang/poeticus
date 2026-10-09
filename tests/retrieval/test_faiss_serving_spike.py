import pytest

from scripts.retrieval.faiss_serving_spike import (
    normalize_nprobes,
    normalize_pq_ms,
    project_full_index_bytes,
    recall_at_k,
    strip_self_neighbors,
)


def test_strip_self_neighbors_removes_query_row_and_keeps_order():
    rows = [
        [3, 7, 9, 11],
        [5, 2, 8, 13],
    ]

    assert strip_self_neighbors(rows, [3, 2], top_k=2) == [
        [7, 9],
        [5, 8],
    ]


def test_recall_at_k_uses_exact_neighbor_overlap():
    exact = [
        [1, 2, 3],
        [4, 5, 6],
    ]
    ann = [
        [1, 8, 3],
        [4, 5, 9],
    ]

    assert recall_at_k(exact, ann, top_k=3) == pytest.approx(2 / 3)


def test_normalize_pq_ms_validates_dimension_and_deduplicates():
    assert normalize_pq_ms([64, 128, 128, 256], dimension=1024) == [
        64,
        128,
        256,
    ]


@pytest.mark.parametrize(
    "pq_ms,dimension",
    [
        ([], 1024),
        ([0], 1024),
        ([96], 1024),
    ],
)
def test_normalize_pq_ms_rejects_invalid_inputs(pq_ms, dimension):
    with pytest.raises(ValueError):
        normalize_pq_ms(pq_ms, dimension=dimension)


def test_normalize_nprobes_clamps_and_deduplicates():
    assert normalize_nprobes([16, 32, 1024, 1024], nlist=512) == [
        16,
        32,
        512,
    ]


@pytest.mark.parametrize(
    "nprobes,nlist",
    [
        ([], 512),
        ([0], 512),
        ([16], 0),
    ],
)
def test_normalize_nprobes_rejects_invalid_inputs(nprobes, nlist):
    with pytest.raises(ValueError):
        normalize_nprobes(nprobes, nlist=nlist)


def test_project_full_index_bytes_separates_fixed_and_per_vector_cost():
    # 测量样本包含 1,000 字节固定开销，每个向量增加 10 字节。
    projected = project_full_index_bytes(
        trained_empty_bytes=1_000,
        populated_sample_bytes=2_000,
        sample_vectors=100,
        full_vectors=1_000,
    )

    assert projected == 11_000


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "trained_empty_bytes": 100,
            "populated_sample_bytes": 90,
            "sample_vectors": 10,
            "full_vectors": 100,
        },
        {
            "trained_empty_bytes": 100,
            "populated_sample_bytes": 100,
            "sample_vectors": 0,
            "full_vectors": 100,
        },
    ],
)
def test_project_full_index_bytes_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        project_full_index_bytes(**kwargs)
