"""离线 C 实验：明确区分精确包含、标点归一化与疑似异文。"""

import pytest

from backend.retrieval.poem.serving import ServingCandidate
from scripts.retrieval.evaluate_self_group_containment import (
    check_remaining_candidates,
    classify_full_work_containment,
    min_substring_edit_distance,
)


def _work(work_id: str, author: str, title: str) -> ServingCandidate:
    return ServingCandidate(
        rank=1, work_id=work_id, title=title, author=author,
        dynasty="宋", source_record_id=work_id,
        text="片片轻鸥落晚沙。",
        chronology_status="same_dynasty", support_count=1,
    )


POEM = (
    "懒向青门学种瓜。只将渔钓送年华。"
    "双双新燕飞春岸，片片轻鸥落晚沙。"
    "歌缥渺，橹呕哑。酒如清露鲊如花。"
    "逢人问道归何处，笑指船儿此是家。"
)
AGGREGATE = (
    "家住东吴近帝乡。平生豪举少年场。十千沽酒青楼上，百万呼卢锦瑟傍。"
    + POEM
    + "南浦舟中两玉人。谁知重见楚江滨。凭教后苑红牙版，引上西川绿锦茵。"
)


def test_exact_full_poem_inside_an_aggregate():
    match = classify_full_work_containment(POEM, AGGREGATE)
    assert (match.method, match.edits) == ("exact", 0)


def test_punctuation_changed_still_matches_after_normalization():
    unpunctuated = "".join(char for char in POEM if char.isalnum())
    match = classify_full_work_containment(unpunctuated, AGGREGATE)
    assert (match.method, match.edits) == ("normalized", 0)


@pytest.mark.parametrize(
    ("modified", "expected_edits"),
    [
        (POEM.replace("落晚沙", "下晚沙"), 1),
        (POEM.replace("落晚沙", "下晚沙").replace("青门", "朱门"), 2),
        (POEM.replace("落晚沙", "落在晚沙"), 1),
        (POEM.replace("落晚沙", "落沙"), 1),
    ],
)
def test_near_variants_are_diagnostic_not_exact(modified: str, expected_edits: int):
    match = classify_full_work_containment(modified, AGGREGATE)
    assert (match.method, match.edits) == ("near", expected_edits)


def test_more_than_two_changes_are_not_matched():
    changed = POEM.replace("懒向", "欲往").replace("青门", "朱门").replace("落晚沙", "下晚沙")
    assert classify_full_work_containment(changed, AGGREGATE).method == "none"


def test_short_or_unrelated_text_cannot_trigger_fuzzy():
    assert classify_full_work_containment("片片轻鸥落晚沙", AGGREGATE).method == "none"
    assert classify_full_work_containment(POEM, "杜甫小寒食舟中作。娟娟戏蝶过闲幔，片片轻鸥下急湍。").method == "none"
    assert classify_full_work_containment(POEM, POEM).method == "none"


def test_same_author_required_for_candidates_even_for_exact_full_containment():
    rows = [
        _work("group", "陆游", "合集"),
        _work("other", "杜甫", "另一首诗"),
    ]
    full = {"group": AGGREGATE, "other": AGGREGATE}
    findings = check_remaining_candidates(
        rows, current_author="陆游", current_text=POEM, work_texts=full,
    )
    assert [(f.work_id, f.method) for f in findings] == [("group", "exact")]


def test_containment_does_not_prove_literary_group_or_self_hit():
    # 故意构造反例：一篇独立长作品全文引用了某首诗；仅凭全文包含不能证明它是合集。
    quoting_work = (
        "诗序：曾经写过这一首，近日重读旧作并且详细记述当时的情况。"
        + POEM
        + "这里是在引用先前作品的全文，然后继续讨论过去和今天的变化。"
    )
    match = classify_full_work_containment(POEM, quoting_work)
    assert match.method == "exact"  # 这是误删风险的证据，不是应该删除的断言。


def test_edit_distance_substring_example_and_negative_cases():
    assert min_substring_edit_distance("懒向青门学种瓜", "另有诗：懒向朱门学种瓜。又一首") == 1
    assert min_substring_edit_distance("懒向青门学种瓜", "不相关的一段文本") is None
    with pytest.raises(ValueError):
        min_substring_edit_distance("", "abc")
    with pytest.raises(ValueError):
        min_substring_edit_distance("abc", "abc", max_edits=-1)
