"""Structural-only EPUB diagnostics use synthetic XHTML, never book excerpts."""

import pytest

from scripts.corpus.epub_import.analyze.inspect_dom_hierarchy import (
    inspect_hierarchy,
)


class Item:
    def __init__(self, raw):
        self.content = raw.encode("utf-8")


class Book:
    def __init__(self, xhtml):
        self.xhtml = xhtml

    def get_item_with_href(self, href):
        return Item(self.xhtml) if href == "x.html" else None


def test_flat_paragraphs_share_parent_without_implying_commentary():
    book = Book(
        '<div class="chapter">'
        '<h2>模拟词牌</h2><p>◆评论原文</p>'
        '<p class="kindle-cn-ref">模拟古籍引文</p>'
        '<p>模拟编者分析</p></div>'
    )
    report = inspect_hierarchy(book, "x.html", ["2-4"])
    assert "直接父节点相同：是" in report
    assert "div.chapter" in report
    assert "kindle-cn-ref" in report
    assert "模拟古籍引文" not in report
    assert "模拟编者分析" not in report
    assert "◆评论原文" not in report


def test_nested_quotation_has_different_direct_parent_but_shared_section():
    book = Book(
        '<section class="commentary">'
        '<p>◆评论原文</p><blockquote><p>模拟引文</p></blockquote>'
        '<p>模拟解说</p></section>'
    )
    report = inspect_hierarchy(book, "x.html", ["1-3"])
    assert "直接父节点相同：否" in report
    assert "section.commentary" in report
    assert "blockquote" in report
    assert "模拟引文" not in report


def test_report_rejects_invalid_and_missing_source_ordinals():
    book = Book("<h2>调</h2><p>句</p>")
    with pytest.raises(ValueError, match="Invalid range"):
        inspect_hierarchy(book, "x.html", ["3-2"])
    with pytest.raises(ValueError, match="not found"):
        inspect_hierarchy(book, "x.html", ["3"])
    with pytest.raises(ValueError, match="not found"):
        inspect_hierarchy(book, "absent.html", ["1"])


def test_an_unrelated_ancestor_is_not_claimed_a_commentary_container():
    book = Book("<p>甲</p><p>乙</p>")
    report = inspect_hierarchy(book, "x.html", ["1-2"])
    assert "直接父节点相同：是" in report
    assert "不证明它在文学语义上是评论容器" in report
