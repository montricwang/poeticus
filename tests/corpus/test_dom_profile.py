"""Synthetic fixtures only: no copyrighted EPUB content in the test suite."""

import sys
from pathlib import Path
from types import ModuleType

# profile_epub_dom imports ebooklib for the CLI; tests use a fake book.
try:
    import ebooklib  # noqa: F401
except ImportError:
    pkg = ModuleType("ebooklib")
    pkg.epub = ModuleType("ebooklib.epub")
    sys.modules["ebooklib"] = pkg
    sys.modules["ebooklib.epub"] = pkg.epub

MODULES = Path(__file__).resolve().parents[2] / "scripts/corpus/epub_import"
sys.path.insert(0, str(MODULES))

from bs4 import BeautifulSoup  # noqa: E402
from css_styles import StyleResolver, local_href  # noqa: E402
from profile_epub_dom import run  # noqa: E402


class Item:
    def __init__(self, text):
        self.data = text.encode("utf-8")

    def get_content(self):
        return self.data


class Book:
    def __init__(self, contents):
        self.contents = contents

    def get_item_with_href(self, name):
        return Item(self.contents[name]) if name in self.contents else None


def fixture():
    book = Book({
        "a.html": '''<html><head><link rel="stylesheet" href="style.css"/></head><body>
            <h2 class="heading"><a id="s1"></a>南歌子<span class="small">八月十八日观潮</span></h2>
            <p class="preface">一段小序。</p><p>正文甲。</p><p>◎注解</p>
            <h2 class="heading">又<span class="small">观潮</span></h2>
            <p>正文乙。</p><div class="odd">其他容器里的文字</div>
            </body></html>''',
        "b.html": '''<html><head><link rel="stylesheet" href="style.css"/></head><body>
            <h2 class="heading">八归<span class="kaiti">湘中送胡德华</span></h2>
            <p class="date">某年（1186）</p><p class="preface">独立题记。</p><p>正文。</p>
            </body></html>''',
        "style.css": '''body {font-family: serif;} h2.heading {font-size: 2em; font-weight: bold;}
            span.small {font-size: .8em;} span.kaiti {font-family: Kai, serif;}
            p.preface {font-style: italic;}''',
    })
    toc = [{"title": "甲词集", "children": [{"title": "作者作品", "children": [
        {"title": "南歌子", "href": "a.html#s1"},
        {"title": "又", "href": "a.html#s1"},
        {"title": "八归", "href": "b.html"},
    ]}]}]
    return book, toc


def test_document_declaration_and_inheritance():
    book, _ = fixture()
    soup = BeautifulSoup(book.get_item_with_href("a.html").get_content(), "lxml")
    styles = StyleResolver(book).for_document(soup, "a.html")
    heading = soup.find("h2")
    span = heading.find("span")
    assert styles.style(heading)["font-size"] == "2em"
    assert styles.style(span)["font-size"] == ".8em"
    assert styles.style(span)["font-weight"] == "bold"
    assert styles.style(span)["font-family"] == "serif"
    assert "style.css" in styles.provenance(span)["font-size"]


def test_profile_finds_heading_templates_and_other_text():
    book, toc = fixture()
    report = run(book, toc)
    volume = report["volumes"][0]
    assert volume["analyzed_files"] == 2  # repeated TOC target is not rescanned
    assert sum(x["count"] for x in volume["heading_templates"]) == 3
    assert any(any(run["element"] == "span.small" for run in x["samples"][0]["runs"])
               for x in volume["heading_templates"])
    assert any(any(run["element"] == "span.kaiti" for run in x["samples"][0]["runs"])
               for x in volume["heading_templates"])
    assert volume["other_text_tags"]["div"] == 1
    assert sum(x["count"] for x in volume["paragraph_templates"]) == 7


def test_css_cascade_and_inline_important():
    book = Book({"t.html": '<link rel="stylesheet" href="s.css"><p class="x" style="font-size: 12px; color: red">字</p>',
                 "s.css": 'p {font-size: 11px !important; color: blue;} p.x {font-style: italic;} '})
    soup = BeautifulSoup(book.contents["t.html"], "lxml")
    style = StyleResolver(book).for_document(soup, "t.html").style(soup.p)
    assert style["font-size"] == "11px"
    assert style["color"] == "red"
    assert style["font-style"] == "italic"


def test_relative_css_paths():
    assert local_href("chapters/a.html", "../css/book.css?v=1") == "css/book.css"
    assert local_href("a.html", "https://example.test/x.css") is None
    assert local_href("a.html", "../../secret.css") is None

def test_original_xhtml_head_is_kept_when_ebooklib_regenerates_content():
    """EpubHtml.get_content() can erase original <head> links; use .content."""
    class EpubHtmlLike(Item):
        def __init__(self, text):
            super().__init__(text)
            self.content = self.data

        def get_content(self):
            return b"<html><head></head><body><h2>Regenerated title</h2></body></html>"

    original = (
        '<html><head><link rel="stylesheet" href="style.css"></head><body>'
        '<h2 class="heading">词牌<span class="small">词题</span></h2></body></html>'
    )
    book = Book({"page.html": original, "style.css": "span.small{font-size:0.5em;}"})
    book.get_item_with_href = lambda name: (
        EpubHtmlLike(original) if name == "page.html" else Item(book.contents[name])
        if name in book.contents else None
    )
    toc = [{"title": "测试词集", "children": [{"title": "卷一", "href": "page.html"}]}]
    report = run(book, toc)
    volume = report["volumes"][0]
    assert volume["linked_css"] == ["style.css"]
    assert volume["heading_templates"][0]["samples"][0]["runs"][1]["text"] == "词题"
    assert volume["heading_templates"][0]["samples"][0]["runs"][1]["style"]["font-size"] == "0.5em"


def test_xml_declaration_is_not_visible_stray_text():
    book = Book({"page.html": "<?xml version='1.0' encoding='utf-8'?><html><body><h2>词牌</h2><p>正文</p></body></html>"})
    toc = [{"title": "甲词集", "children": [{"title": "卷一", "href": "page.html"}]}]
    report = run(book, toc)
    assert "[document]" not in report["volumes"][0]["other_text_tags"]
