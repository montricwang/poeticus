"""Full paragraph glyph-context export tested only with invented content."""
import re

import pytest
from bs4 import BeautifulSoup

from scripts.corpus.epub_import.review.glyph_contexts import (
    collect_glyph_paragraphs,
    render_contexts_html,
    write_contexts,
)


class Item:
    def __init__(self, content):
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")


class Book:
    def __init__(self, items):
        self.items = items

    def get_item_with_href(self, href):
        val = self.items.get(href)
        return Item(val) if val is not None else None


REPORT = {
    "collections": [{
        "collection": "合成词集", "slug": "test",
        "missing_glyphs": [
            {"html": "x.html", "src": "glyph1.png"},
            {"html": "x.html", "src": "glyph2.png"},
            {"html": "y.html", "src": "glyph1.png"},
        ],
    }],
}


def sample_book():
    return Book({
        "x.html": (
            "<h2>合成词牌</h2>"
            "<p>甲<img src='glyph1.png'/>乙<img src='glyph2.png'/>丙</p>"
            "<p>再有<img src='glyph1.png'/>和<img src='glyph1.png'/>。</p>"
        ),
        "y.html": "<h2>别首</h2><p>句首<img src='glyph1.png'/>句末</p>",
        "glyph1.png": b"synthetic bytes",
        "glyph2.png": b"another synthetic bytes",
    })


def test_same_image_review_id_has_all_paragraphs_and_repeat_positions():
    cases, sites = collect_glyph_paragraphs(REPORT, sample_book())
    assert [(c["src"], c["pages"]) for c in cases] == [
        ("glyph1.png", ["x.html", "y.html"]),
        ("glyph2.png", ["x.html"]),
    ]
    assert [(a["html"], a["block"], a["occurrences"]) for a in sites[1]] == [
        ("x.html", 2, 1), ("x.html", 3, 2), ("y.html", 2, 1),
    ]
    assert sites[1][0]["paragraph"].count('class="target"') == 1
    assert sites[1][0]["paragraph"].count('class="other"') == 1
    assert sites[1][1]["paragraph"].count('class="target"') == 2
    assert sites[2][0]["paragraph"].count('class="target"') == 1
    assert sites[1][0]["heading"] == "合成词牌"


def test_html_standalone_includes_each_source_paragraph_and_own_image(tmp_path):
    output = tmp_path / "glyph_contexts.html"
    write_contexts(REPORT, sample_book(), output)
    document = BeautifulSoup(output.read_text(encoding="utf-8"), "html.parser")
    sections = document.select("section.card")
    assert len(sections) == 2
    assert sections[0]["id"] == "glyph-001"
    assert sections[1]["id"] == "glyph-002"
    assert len(sections[0].select(".source")) == 3
    assert len(sections[1].select(".source")) == 1
    assert len(sections[0].select("mark.target")) == 4
    assert len(sections[0].select("mark.other")) == 1
    assert len(sections[1].select("mark.target")) == 1
    assert sections[0].select_one("img")["src"].startswith(
        "data:image/png;base64,"
    )
    assert "甲" in sections[0].get_text()
    assert "句末" in sections[0].get_text()
    assert "完整段落" in document.title.get_text()
    assert "仅限本地" in document.get_text()


def test_fails_if_preflight_ref_cannot_be_found_in_source():
    book = Book({
        "x.html": "<h2>词牌</h2><p>普通正文没有图片字</p>",
        "y.html": "<h2>词牌</h2><p>其他文字</p>",
        "glyph1.png": b"fake", "glyph2.png": b"fake",
    })
    with pytest.raises(RuntimeError, match="找不到包含该图片"):
        collect_glyph_paragraphs(REPORT, book)


def test_heading_images_rendered_and_paragraph_text_escaped():
    report = {"collections": [{
        "collection": "甲册", "slug": "book",
        "missing_glyphs": [{"html": "title.html", "src": "glyph.jpg"}],
    }]}
    book = Book({
        "title.html": (
            '<h2>标题<img src="glyph.jpg"/>尾</h2>'
            '<p>合成词句里有 &lt; 小于号</p>'
        ),
        "glyph.jpg": b"demo",
    })
    result = render_contexts_html(report, book)
    soup = BeautifulSoup(result, "html.parser")
    assert len(soup.select("mark.target")) == 1
    assert soup.select_one(".paragraph").get_text() == "标题〔图片字 001〕尾"
    assert "标题" in soup.select_one(".meta").get_text()
    assert len(re.findall(r'data:image/jpeg;base64,', result)) == 1
