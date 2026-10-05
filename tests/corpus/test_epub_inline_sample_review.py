"""Synthetic sample selection: only locations escape private source output."""
import pytest

from scripts.corpus.epub_import.diagnostics.inspect_inline_samples import (
    render_plan,
    render_private_packet,
    select_inline_samples,
)


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")


class Book:
    def __init__(self, sources):
        self.sources = sources

    def get_item_with_href(self, name):
        value = self.sources.get(name)
        return Item(value) if value else None


def site(collection, html, block, family, *, gap=False):
    return {
        "collection": collection,
        "html": html,
        "block": block,
        "warned": True,
        "style_signatures": [f"span class={family} style=-"],
        "paragraph_classes": [],
        "styled_spans": 1,
        "has_gap_marker": gap,
    }


def test_samples_choose_both_collections_before_repeating_a_style():
    audit = {"sites": [
        site("南唐", "a.html", 2, "kaiti", gap=True),
        site("纳兰", "b.html", 2, "kaiti"),
        site("纳兰", "b.html", 4, "kaiti"),
        site("纳兰", "b.html", 6, "kaiti"),
        site("黄庭坚", "c.html", 2, "font1"),
        site("辛弃疾", "d.html", 2, "font1"),
        site("辛弃疾", "d.html", 4, "font1"),
    ]}
    picks = select_inline_samples(audit, per_style=3)
    assert [p["case_id"] for p in picks] == [
        "kaiti-01", "kaiti-02", "kaiti-03",
        "font1-01", "font1-02", "font1-03",
    ]
    assert [p["collection"] for p in picks[:2]] == ["南唐", "纳兰"]
    assert [p["collection"] for p in picks[3:5]] == ["黄庭坚", "辛弃疾"]
    assert len({(p["html"], p["block"]) for p in picks}) == 6
    assert select_inline_samples(audit, families=("kaiti",), per_style=2) == picks[:2]
    with pytest.raises(ValueError, match="per_style"):
        select_inline_samples(audit, per_style=0)


def test_public_plan_does_not_copy_source_but_private_view_does():
    data = {"sites": [site("南唐", "a.html", 2, "kaiti")]}
    picks = select_inline_samples(data, families=("kaiti",))
    book = Book({"a.html": (
        "<h2>合成词牌</h2>"
        "<p>实验正文甲<span class='kaiti'>实验说明</span>实验正文乙</p>"
    )})
    public = render_plan(picks)
    assert "a.html" in public
    assert "kaiti-01" in public
    assert "实验说明" not in public
    assert "原始 XHTML" not in public
    private = render_private_packet(book, picks)
    assert "实验说明" in private
    assert '<span class="kaiti">' in private
    assert "实验正文甲" in private
    assert "切勿公开" in private


def test_unknown_family_gives_clear_empty_plan():
    assert "没有找到候选" in render_plan(
        select_inline_samples({"sites": []}, families=("kaiti",))
    )



def test_remaining_flag_skips_real_checked_coordinates_only():
    audit = {"sites": [
        site("黄庭坚", "text00214.html", 696, "font1"),
        site("辛弃疾", "text00279.html", 243, "font1"),
        site("辛弃疾", "text00279.html", 777, "font1"),
        site("黄庭坚", "text00214.html", 999, "font1"),
        site("纳兰", "unknown.html", 23, "kaiti"),
    ]}
    remaining = select_inline_samples(
        audit, families=("font1",), per_style=15, remaining=True,
    )
    assert [(case["html"], case["block"]) for case in remaining] == [
        ("text00279.html", 777),
        ("text00214.html", 999),
    ]
    assert len(select_inline_samples(
        audit, families=("font1",), per_style=15
    )) == 4
    assert len(select_inline_samples(
        audit, families=("kaiti",), remaining=True
    )) == 1
