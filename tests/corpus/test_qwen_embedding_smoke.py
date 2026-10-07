import math

import pytest

from scripts.corpus.qwen_embedding_smoke import (
    cosine_similarity,
    rank_candidates,
)


def test_cosine_similarity_handles_basic_geometry():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_rejects_invalid_vectors():
    with pytest.raises(ValueError, match="维度"):
        cosine_similarity([1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="空向量"):
        cosine_similarity([], [])
    with pytest.raises(ValueError, match="零向量"):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])


def test_rank_candidates_sorts_by_cosine():
    rows = rank_candidates(
        [1.0, 0.0],
        [
            [0.2, math.sqrt(0.96)],
            [1.0, 0.0],
            [0.8, 0.6],
        ],
        ["弱相关", "完全相同", "较相关"],
    )

    assert [row["text"] for row in rows] == [
        "完全相同",
        "较相关",
        "弱相关",
    ]


def test_rank_candidates_requires_matching_counts():
    with pytest.raises(ValueError, match="数量"):
        rank_candidates([1.0], [[1.0]], ["甲", "乙"])
