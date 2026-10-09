"""来源块的类型契约必须保留合成 DOM 证据格式。"""

from bs4 import BeautifulSoup, Tag

from scripts.corpus.epub_import.extractor.blocks import (
    inline_runs,
    iter_source_blocks,
)
from scripts.corpus.epub_import.extractor.extractor import paragraph_text


def test_source_blocks_keep_locations_and_inline_evidence():
    soup = BeautifulSoup(
        '<html><body><h2 id="heading" class="tune small">'
        '词牌<span class="small" style="font-size:.5em">副题</span>'
        '</h2><p>正文<img src="glyph.png"/>下句<br/>收束</p></body></html>',
        "lxml",
    )

    blocks = list(iter_source_blocks(soup, "chapter.xhtml"))
    assert len(blocks) == 2
    assert blocks[0].location() == {
        "html": "chapter.xhtml",
        "block": 1,
        "tag": "h2",
        "classes": ["tune", "small"],
        "anchor": "heading",
    }
    assert blocks[0].runs == [
        {"tag": "text", "text": "词牌"},
        {
            "tag": "span",
            "classes": ["small"],
            "style": "font-size:.5em",
            "text": "副题",
        },
    ]
    assert blocks[1].runs == [
        {"tag": "text", "text": "正文"},
        {"tag": "img", "src": "glyph.png"},
        {"tag": "text", "text": "下句"},
        {"tag": "br", "text": "\n"},
        {"tag": "text", "text": "收束"},
    ]


def test_inline_runs_preserve_missing_image_source_as_empty_string():
    soup = BeautifulSoup("<p>开头<img/>末尾</p>", "lxml")
    paragraph = soup.find("p")
    assert isinstance(paragraph, Tag)
    assert inline_runs(paragraph) == [
        {"tag": "text", "text": "开头"},
        {"tag": "img", "src": ""},
        {"tag": "text", "text": "末尾"},
    ]


def test_paragraph_text_preserves_missing_glyph_and_linebreak():
    soup = BeautifulSoup("<p>前<img/>后<br/>末</p>", "lxml")
    paragraph = soup.find("p")
    assert isinstance(paragraph, Tag)

    text, warnings = paragraph_text(paragraph, "part.xhtml", "text")
    assert text == "前{{glyph:missing-src}}后\n末"
    assert warnings == [
        {
            "type": "missing_image_src",
            "html": "part.xhtml",
            "src": None,
            "category": "text",
            "status": "unresolved",
        }
    ]
    assert paragraph.find("img") is not None
