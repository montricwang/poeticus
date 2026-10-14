"""Post-Eligibility 组诗去重实验：只压制有真实全文包含证据的候选。"""
from backend.retrieval.poem.serving import ServingCandidate
from scripts.retrieval.evaluate_group_candidate_filter import (
    suppress_retrieved_group_duplicates,
)


def _candidate(work_id: str, author: str, title: str, text: str) -> ServingCandidate:
    return ServingCandidate(
        rank=1, work_id=work_id, author=author, title=title, text=text,
        dynasty="宋", source_record_id=work_id,
        chronology_status="same_dynasty", support_count=1,
    )


def test_suppress_retrieved_aggregate_and_refill_without_reranking():
    poem = "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。"
    corpus = {
        "group": "家住东吴近帝乡。平生豪举少年场。" + poem,
        "single": poem,
        "dufu": "娟娟戏蝶过闲幔，片片轻鸥下急湍。",
        "filler": "其他真实作品正文，该作品不会与当前案例混合。",
    }
    rows = [
        _candidate("group", "陆游", "鹧鸪天 送叶梦锡", "片片轻鸥落晚沙。"),
        _candidate("single", "陆游", "鹧鸪天 其六", "片片轻鸥落晚沙。"),
        _candidate("dufu", "杜甫", "小寒食舟中作", "片片轻鸥下急湍。"),
        _candidate("filler", "甲", "其他", "其他真实作品正文"),
    ]
    filtered = suppress_retrieved_group_duplicates(
        rows, corpus, final_top_k=3, comparison_window=3,
    )
    assert [x.work_id for x in filtered.candidates] == ["single", "dufu", "filler"]
    assert [(x.suppressed_work_id, x.kept_work_id) for x in filtered.suppressed] == [
        ("group", "single"),
    ]


def test_do_not_remove_similar_but_independent_works():
    phrase = "片片轻鸥落晚沙。"
    texts = {
        "one": "懒向青门学种瓜。" + phrase,
        "two": "那一年偶有轻鸥飞过江沙。" + phrase + "却未知道归期。",
    }
    rows = [
        _candidate("one", "陆游", "其一", phrase),
        _candidate("two", "陆游", "其二", phrase),
    ]
    result = suppress_retrieved_group_duplicates(
        rows, texts, final_top_k=2,
    )
    assert [c.work_id for c in result.candidates] == ["one", "two"]
    assert result.suppressed == ()


def test_no_shorter_candidate_no_guess_or_replacement():
    poem = "懒向青门学种瓜。只将渔钓送年华。"
    group = _candidate("group", "陆游", "七首合集", "懒向青门学种瓜。")
    rows = [group, _candidate("dufu", "杜甫", "小寒食", "片片轻鸥下急湍。")]
    result = suppress_retrieved_group_duplicates(
        rows, {"group": "其他篇章。" + poem},
        final_top_k=2,
    )
    assert result.candidates == tuple(rows)
    assert result.suppressed == ()


def test_different_author_and_missing_full_work_never_suppress():
    shared = "桃花流水窅然去。"
    texts = {"a": shared + "春风吹绿门前柳。",
             "b": "题序：" + shared + "春风吹绿门前柳。"}
    rows = [
        _candidate("a", "陆游", "独立诗", shared),
        _candidate("b", "李白", "长诗", shared),
    ]
    assert not suppress_retrieved_group_duplicates(
        rows, texts, final_top_k=2,
    ).suppressed
    rows[1] = _candidate("b", "陆游", "长诗", shared)
    assert not suppress_retrieved_group_duplicates(
        rows, {"a": texts["a"]}, final_top_k=2,
    ).suppressed


def test_suppress_only_when_hit_is_actually_shared():
    full = "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。"
    rows = [
        _candidate("group", "陆游", "组诗", "前一首别的诗句。"),
        _candidate("member", "陆游", "其六", "懒向青门学种瓜。"),
    ]
    result = suppress_retrieved_group_duplicates(
        rows, {"group": "前一首别的诗句。" + full, "member": full},
        final_top_k=2,
    )
    assert result.suppressed == ()


def test_comparison_window_limits_suppression_and_validates_bounds():
    from pytest import raises

    poem = "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。"
    rows = [
        _candidate("group", "陆游", "组诗", "懒向青门学种瓜。"),
        _candidate("other", "李白", "其他", "天边远望青山在。"),
        _candidate("member", "陆游", "其六", "懒向青门学种瓜。"),
    ]
    texts = {"group": "别首。" + poem, "member": poem}
    a = suppress_retrieved_group_duplicates(
        rows, texts, final_top_k=2, comparison_window=2,
    )
    b = suppress_retrieved_group_duplicates(
        rows, texts, final_top_k=2, comparison_window=3,
    )
    assert not a.suppressed
    assert [v.work_id for v in b.candidates] == ["other", "member"]
    with raises(ValueError):
        suppress_retrieved_group_duplicates(
            rows, texts, final_top_k=3, comparison_window=2,
        )
