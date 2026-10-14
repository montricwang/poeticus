import hashlib

import pytest

from backend.retrieval.poem.chronology import (
    KNOWN_DYNASTIES,
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


def test_overlap_is_not_transitive_across_parallel_dynasties():
    # 两段「可能同时存在」不能串起来当成另一段重叠。
    assert classify_dynasty_relation("辽", "宋") == "overlapping"
    assert classify_dynasty_relation("宋", "元") == "overlapping"
    assert classify_dynasty_relation("辽", "元") == "clearly_earlier"
    assert classify_dynasty_relation("元", "辽") == "clearly_later"


def test_corpus_label_classifier_preserves_existing_729_pair_decisions():
    """对 27 个 Werneror 标签的旧版判断作完整快照，避免隐藏行为漂移。"""
    labels = sorted(KNOWN_DYNASTIES)
    assert len(labels) == 27
    serialized = "|".join(
        classify_dynasty_relation(candidate, target)
        for candidate in labels
        for target in labels
    )
    assert hashlib.sha256(serialized.encode()).hexdigest() == (
        "bad632c6fedc3518efb30b76da20df409e540de6e8339fdbfb48ba0b3ba8a9f9"
    )


def test_legacy_diagnostic_prior_selection_remains_unchanged_for_all_labels():
    """老脚本的严格前代选择与产品宽松筛选不能在重构时混为一谈。"""
    labels = sorted(KNOWN_DYNASTIES)
    serialized = "|".join(
        ",".join(sorted(candidate_prior_dynasties(target)))
        for target in labels
    )
    assert hashlib.sha256(serialized.encode()).hexdigest() == (
        "8a7a75a6e04ffb5be963d4a0a51420b36e8d787a4793296e7f4ededd6367e843"
    )
