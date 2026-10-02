"""Synthetic human-review sampling tests, no commercial text in git."""
import pytest

from scripts.corpus.epub_import.analyze.sample_classification import (
    build_candidates,
    choose_batch,
    plan_markdown,
    private_packet_markdown,
)


class Item:
    def __init__(self, value):
        self.content = value.encode("utf-8")


class Book:
    def __init__(self, html_files):
        self.html_files = html_files

    def get_item_with_href(self, name):
        if name not in self.html_files:
            return None
        return Item(self.html_files[name])


SPECS = [
    ("温庭筠词集·韦庄词集", "温庭筠", "wen-wei"),
    ("周邦彦词集", "周邦彦", "zhou-bangyan"),
    ("辛弃疾词集", "辛弃疾", "xin-qiji"),
]
TOC = [
    {"title": name, "children": [
        {"title": "作品", "href": html},
    ]}
    for (name, _, _), html in zip(SPECS, ["wen.html", "zhou.html", "xin.html"])
]
BOOK = Book({
    "wen.html": (
        "<h2>菩萨蛮</h2><p>合成正文甲</p>"
        '<p class="review">◆合成评论开头</p>'
        '<p class="review">合成评论续段</p>'
        "<h2>渔歌子</h2><p>合成普通词正文</p>"
    ),
    "zhou.html": (
        "<h2>瑞龙吟</h2><p>合成正文乙</p>"
        '<p class="note">◎合成注释开头</p>'
        '<p class="note">合成注释续段</p>'
    ),
    "xin.html": (
        "<h2>摸鱼儿</h2><p>前半句"
        '<span style="font-size:70%">合成行内文字</span>后半句</p>'
        "<h2>西江月</h2>"
        '<p class="kindle-cn-ref">合成小序</p>'
        "<p>合成正文丙</p><p>◆合成评论</p>"
    ),
})


def test_sampler_covers_warning_types_and_success_controls_without_duplicate_sites():
    pools = build_candidates(BOOK, TOC, SPECS)
    assert len(pools["inferred_commentary"]) == 1
    assert len(pools["inferred_annotation"]) == 1
    assert len(pools["inline_style"]) == 1
    assert len(pools["clean_complex"]) == 1
    assert len(pools["clean_plain"]) == 1
    cases, counts = choose_batch(pools)
    assert [c["kind"] for c in cases] == [
        "inferred_commentary", "inferred_annotation", "inline_style",
        "clean_complex", "clean_plain",
    ]
    assert [c["block"] for c in cases[:3]] == [4, 4, 2]
    assert [counts[c["kind"]] for c in cases] == [1] * 5
    assert len({(c["html"], c["block"]) for c in cases}) == 5
    assert cases[0]["case_id"] == "R01-01"


def test_public_plan_only_includes_locations_not_private_paragraphs():
    cases, counts = choose_batch(build_candidates(BOOK, TOC, SPECS), limit=3)
    safe = plan_markdown(cases, counts, round_number=1)
    sensitive = [
        "合成评论续段", "合成注释续段",
        "合成行内文字", "合成小序",
    ]
    assert all(term not in safe for term in sensitive)
    assert "现有分类" in safe
    assert "请判断" in safe
    assert "不是分类正确率估计" in safe
    assert "text" not in safe or "block" not in safe
    local = private_packet_markdown(BOOK, cases)
    assert "合成评论续段" in local
    assert "合成注释续段" in local
    assert "合成行内文字" in local
    assert "原始段落快速查询" in local
    assert "请勿公开" in local


def test_round_rotation_is_stable_and_validated():
    pool = {
        "inferred_commentary": [
            {"kind": "inferred_commentary",
             "collection": "测试册", "html": "a.html", "block": i,
             "poem_id": f"p{i}", "tune": "调", "role": "note_continuation"}
            for i in range(14)
        ],
    }
    a, _ = choose_batch(pool, round_number=1, limit=1)
    b, _ = choose_batch(pool, round_number=2, limit=1)
    assert a[0]["block"] == 0
    assert b[0]["block"] == 7
    assert choose_batch(pool, round_number=2, limit=1)[0] == b
    with pytest.raises(ValueError):
        choose_batch(pool, round_number=0)
    with pytest.raises(ValueError):
        choose_batch(pool, limit=0)
    with pytest.raises(ValueError):
        choose_batch(pool, limit=21)


def test_empty_candidate_pool_is_explained_without_crashing():
    cases, counts = choose_batch({key: [] for key in (
        "inferred_commentary", "inferred_annotation", "inline_style",
        "clean_complex", "clean_plain",
    )})
    assert cases == []
    assert counts["inline_style"] == 0
    assert "没有符合当前抽样类别的样本" in plan_markdown(cases, counts)
