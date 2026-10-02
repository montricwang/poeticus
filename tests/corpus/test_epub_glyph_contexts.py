"""Only invented text in tests for local glyph context lookup."""
from scripts.corpus.epub_import.review_glyph_contexts import (
    find_contexts,
    render_contexts,
)


class Item:
    def __init__(self, contents):
        self.content = contents.encode("utf-8")


class Book:
    def __init__(self, files):
        self.files = files

    def get_item_with_href(self, name):
        return Item(self.files[name]) if name in self.files else None


def test_source_contexts_are_short_bounded_and_cover_multiple_glyphs():
    book = Book({"demo.html": (
        "<h2>合成调名</h2><p>前缀十二字"
        "<img src='a.jpg'/>夹心"
        "<img src='b.jpg'/>后缀九字</p>"
    )})
    sites = [
        {"slug": "book", "src": "a.jpg", "pages": ["demo.html"]},
        {"slug": "book", "src": "b.jpg", "pages": ["demo.html"]},
    ]
    result = find_contexts(book, sites, window=3)
    assert len(result) == 2
    first = result[0]["examples"][0]
    assert first["before"] == "十二字"
    assert first["after"].startswith("夹心")
    assert "后缀九字" not in first["after"]
    assert result[1]["examples"][0]["before"].endswith("夹心")
    md = render_contexts(result)
    assert "001 · book · a.jpg" in md
    assert "002 · book · b.jpg" in md
    assert "⟦目标字⟧" in md
    assert "合成调名" not in md


def test_identical_image_twice_and_not_found_are_explicit():
    book = Book({"x.html": (
        "<h2>调名</h2><p>甲<img src='same.jpg'/>乙"
        "<img src='same.jpg'/>丙</p>"
    )})
    sites = [
        {"slug": "s", "src": "same.jpg", "pages": ["x.html"]},
        {"slug": "s", "src": "absent.jpg", "pages": ["x.html"]},
    ]
    rows = find_contexts(book, sites, window=5, max_examples=2)
    assert len(rows[0]["examples"]) == 2
    assert rows[1]["examples"] == []
    assert "未定位到文字段落" in render_contexts(rows)


def test_arguments_reject_unbounded_source_excerpt():
    import pytest
    with pytest.raises(ValueError):
        find_contexts(Book({}), [], window=200)
    with pytest.raises(ValueError):
        find_contexts(Book({}), [], max_examples=100)
