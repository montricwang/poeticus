import pytest

from backend.retrieval.chronology import (
    candidate_prior_dynasties,
    classify_dynasty_relation,
)


@pytest.mark.parametrize(
    ("candidate", "target", "expected"),
    [
        ("唐", "宋", "clearly_earlier"),
        ("明", "宋", "clearly_later"),
        ("宋", "宋", "same_dynasty"),
        ("辽", "宋", "overlapping"),
        ("唐末宋初", "宋", "overlapping"),
        ("元", "宋", "overlapping"),
        (None, "宋", "unknown"),
        ("宋", None, "unknown"),
        ("未知", "宋", "unknown"),
    ],
)
def test_classify_dynasty_relation_is_conservative(candidate, target, expected):
    assert classify_dynasty_relation(candidate, target) == expected


def test_legacy_candidate_prior_dynasties_keeps_existing_diagnostic_semantics():
    allowed = candidate_prior_dynasties("宋")

    assert "唐" in allowed
    assert "唐末宋初" in allowed
    assert "宋" not in allowed
    assert "辽" not in allowed


def test_candidate_prior_dynasties_rejects_unknown_target():
    with pytest.raises(ValueError, match="尚未定义"):
        candidate_prior_dynasties("未知")
