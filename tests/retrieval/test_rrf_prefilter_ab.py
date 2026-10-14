"""#279：诗歌业务资格规则只定义一次，离线对照不触碰生产排序。"""
import math

from backend.retrieval.poem.pipeline.fanout import (
    ChannelDescriptor,
    QueryChannelResult,
    RetrievalHit,
)
from backend.retrieval.poem.pipeline.query_strategy import build_query_plan
from backend.retrieval.poem.pipeline.eligibility import classify_work_eligibility
from scripts.retrieval.rrf_prefilter_ab import (
    compare_rankings,
    filter_and_renumber_works,
)


def _rankings(channel: str, *rows: tuple[str, str | None, str]) -> QueryChannelResult:
    query = build_query_plan("片片轻鸥落晚沙。")[0]
    return QueryChannelResult(
        query=query,
        channel=ChannelDescriptor(
            name=channel,
            method="dense" if channel == "dense" else "lexical",
            chunk_policy="sentence",
        ),
        hits=tuple(
            RetrievalHit(
                rank=index,
                chunk_id=f"{work_id}:{index}",
                work_id=work_id,
                text=chunk,
                author="作者",
                dynasty=dynasty,
            )
            for index, (work_id, dynasty, chunk) in enumerate(rows, 1)
        ),
    )


def test_pre_fusion_removes_invalid_chunks_deduplicates_works_and_renumbers():
    raw = _rankings(
        "dense",
        ("self", "宋", "当前作品"),
        ("later", "明", "晚出作品"),
        ("dufu", "唐", "娟娟戏蝶过闲幔"),
        ("dufu", "唐", "片片轻鸥下急湍"),
        ("other", "宋", "同朝另作"),
        ("uncertain", None, "未知朝代"),
        ("overlap", "辽", "时间交叠"),
    )
    cleaned, diagnostics = filter_and_renumber_works(
        [raw],
        self_work_ids={"self"},
        target_dynasty="宋",
    )
    assert [h.work_id for h in cleaned[0].hits] == [
        "dufu", "other", "uncertain", "overlap",
    ]
    assert [h.rank for h in cleaned[0].hits] == [1, 2, 3, 4]
    assert cleaned[0].hits[0].text == "娟娟戏蝶过闲幔"
    assert [h.rank for h in raw.hits] == list(range(1, 8))
    assert diagnostics[0]["self_hit_chunks"] == 1
    assert diagnostics[0]["clearly_later_chunks"] == 1
    assert diagnostics[0]["duplicate_eligible_chunks"] == 1
    assert diagnostics[0]["first_eligible_raw_rank"] == 3


def test_work_rule_does_not_remove_same_author_other_work():
    relation, rejection = classify_work_eligibility(
        "other-work",
        "宋",
        self_work_ids={"current-work"},
        target_dynasty="宋",
    )
    assert (relation, rejection) == ("same_dynasty", None)


def test_same_input_a_b_rrf_changes_scores_without_changing_eligible_pool():
    raw = [
        _rankings(
            "dense",
            ("self", "宋", "当前作品"),
            ("later", "明", "晚出作品"),
            ("dufu", "唐", "片片轻鸥下急湍"),
            ("other", "宋", "其他候选"),
        ),
        _rankings(
            "lexical",
            ("other", "宋", "其他候选"),
            ("later", "明", "晚出作品"),
            ("dufu", "唐", "片片轻鸥下急湍"),
        ),
    ]
    result = compare_rankings(
        raw,
        self_work_ids={"self"},
        target_dynasty="宋",
        final_top_k=1,
    )
    a = result["a"]
    b = result["b"]
    assert {x.work_id for x in a} == {x.work_id for x in b} == {"dufu", "other"}
    assert len(a) == len(b) == 2  # 对照时不得先截成最终 Top-1
    a_dufu = next(x for x in a if x.work_id == "dufu")
    b_dufu = next(x for x in b if x.work_id == "dufu")
    assert math.isclose(a_dufu.rrf_score, 1 / 63 + 1 / 63)
    assert math.isclose(b_dufu.rrf_score, 1 / 61 + 1 / 62)
    assert a_dufu.support_count == b_dufu.support_count == 2
    assert [h.rank for r in raw for h in r.hits] == [1, 2, 3, 4, 1, 2, 3]


def test_no_invalid_candidates_and_unknown_chronology_still_kept():
    rows = [_rankings(
        "dense",
        ("self", "宋", "自身"),
        ("later", "明", "后世"),
        ("unknown", "不详", "不详朝代"),
    )]
    result = compare_rankings(rows, self_work_ids={"self"}, target_dynasty="宋")
    assert [c.work_id for c in result["a"]] == ["unknown"]
    assert [c.work_id for c in result["b"]] == ["unknown"]
