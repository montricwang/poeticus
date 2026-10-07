from backend.retrieval.eligibility import apply_candidate_eligibility
from backend.retrieval.fusion import FusedCandidate


def _candidate(work_id, *, dynasty):
    return FusedCandidate(
        work_id=work_id,
        title=work_id,
        author="作者",
        dynasty=dynasty,
        source_record_id=f"source:{work_id}",
        rrf_score=1.0,
        best_rank=1,
        support_count=1,
        evidences=(),
    )


def test_eligibility_rejects_current_work_even_when_chronology_is_uncertain():
    result = apply_candidate_eligibility(
        [
            _candidate("current", dynasty="宋"),
            _candidate("other", dynasty="宋"),
        ],
        current_work_id="current",
        target_dynasty="宋",
    )

    assert [item.candidate.work_id for item in result.eligible] == ["other"]
    assert result.eligible[0].chronology_status == "same_dynasty"
    assert [(item.candidate.work_id, item.reason) for item in result.rejected] == [
        ("current", "self_hit")
    ]


def test_eligibility_rejects_only_clearly_later_dynasties():
    result = apply_candidate_eligibility(
        [
            _candidate("tang", dynasty="唐"),
            _candidate("song", dynasty="宋"),
            _candidate("liao", dynasty="辽"),
            _candidate("ming", dynasty="明"),
        ],
        current_work_id=None,
        target_dynasty="宋",
    )

    assert [
        (item.candidate.work_id, item.chronology_status)
        for item in result.eligible
    ] == [
        ("tang", "clearly_earlier"),
        ("song", "same_dynasty"),
        ("liao", "overlapping"),
    ]
    assert [
        (item.candidate.work_id, item.reason)
        for item in result.rejected
    ] == [("ming", "clearly_later")]


def test_eligibility_keeps_unknown_chronology_for_recall():
    result = apply_candidate_eligibility(
        [_candidate("unknown", dynasty=None)],
        current_work_id=None,
        target_dynasty="宋",
    )

    assert len(result.eligible) == 1
    assert result.eligible[0].chronology_status == "unknown"
    assert result.rejected == ()


def test_eligibility_preserves_fused_candidate_order():
    candidates = [
        _candidate("first", dynasty="唐"),
        _candidate("later", dynasty="明"),
        _candidate("second", dynasty="宋"),
    ]

    result = apply_candidate_eligibility(
        candidates,
        current_work_id=None,
        target_dynasty="宋",
    )

    assert [item.candidate.work_id for item in result.eligible] == [
        "first",
        "second",
    ]


def test_eligibility_rejects_all_known_current_work_aliases():
    result = apply_candidate_eligibility(
        [
            _candidate("current-a", dynasty="宋"),
            _candidate("current-b", dynasty="宋"),
            _candidate("other", dynasty="宋"),
        ],
        current_work_id="current-a",
        current_work_ids={"current-a", "current-b"},
        target_dynasty="宋",
    )

    assert [item.candidate.work_id for item in result.eligible] == ["other"]
    assert [
        (item.candidate.work_id, item.reason)
        for item in result.rejected
    ] == [
        ("current-a", "self_hit"),
        ("current-b", "self_hit"),
    ]
