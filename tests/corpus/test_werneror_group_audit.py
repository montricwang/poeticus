"""Corpus 组诗审计只读逻辑：精确整篇串接的正反例。"""
from collections import defaultdict
from scripts.corpus.werneror_group_audit import (
    PREFIX_LEN,
    Work,
    find_exact_components,
)


def _work(number: int, author: str, content: str) -> Work:
    return Work(
        work_id=f"work-{number}", source_record_id=f"test:{number}",
        title=f"题目{number}", author=author, dynasty="宋", content=content,
    )


def _matching(host: Work, *members: Work) -> list[Work] | None:
    works = [host, *members]
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, item in enumerate(works):
        index[(item.author, item.content[:PREFIX_LEN])].append(i)
    return find_exact_components(host, works, index, min_piece=24)


def test_find_full_concatenation_in_order():
    a = _work(1, "陆游", "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。")
    b = _work(2, "陆游", "歌缥渺，橹呕哑。酒如清露鲊如花。逢人问道归何处，笑指船儿此是家。")
    c = _work(3, "陆游", "家住东吴近帝乡。平生豪举少年场。十千沽酒青楼上，百万呼卢锦瑟傍。")
    host = _work(4, "陆游", a.content + b.content + c.content)
    assert _matching(host, a, b, c) == [a, b, c]


def test_long_single_work_is_not_aggregate_without_exact_full_coverage():
    member = _work(1, "陆游", "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。")
    host = _work(2, "陆游", "长诗自己的一大段序。" + member.content + "长诗后面还有独立内容。")
    assert _matching(host, member) is None


def test_author_boundary_and_truncated_poem():
    a = _work(1, "杜甫", "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。")
    b = _work(2, "陆游", "歌缥渺，橹呕哑。酒如清露鲊如花。逢人问道归何处，笑指船儿此是家。")
    host = _work(3, "陆游", a.content + b.content)
    assert _matching(host, a, b) is None


def test_rejects_partial_match_or_one_same_length_version():
    a = _work(1, "陆游", "懒向青门学种瓜。只将渔钓送年华。双双新燕飞春岸，片片轻鸥落晚沙。")
    same = _work(2, "陆游", a.content)
    assert _matching(a, same) is None
    host = _work(3, "陆游", a.content + "下一首独立作品尚未收录。")
    assert _matching(host, a) is None
