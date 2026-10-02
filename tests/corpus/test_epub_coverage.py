"""Synthetic source-block coverage tests: no copyrighted EPUB passages."""
from scripts.corpus.epub_import.analyze.coverage import source_block_coverage
from scripts.corpus.epub_import.analyze.audit_extraction import audit_collection, render_md
from scripts.corpus.epub_import.extractor.extractor import extract_sections


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")


class Book:
    def __init__(self, files):
        self.files = files

    def get_item_with_href(self, href):
        return Item(self.files[href]) if href in self.files else None


def test_coverage_distinguishes_explicit_editorial_skips_from_untracked_prose():
    book = Book({"x.html": (
        "<h1>导读</h1><h2>专题</h2><p>编辑导读文字</p>"
        "<h1>词卷</h1><p>未被抽取的游离段落</p>"
        "<h2>浣溪沙</h2><p>合成词句</p>"
        "<h2>总评</h2><p>编辑总评文字</p>"
    )})
    sections = extract_sections(book, "x.html", "柳永词集")
    report = source_block_coverage(book, ["x.html"], sections, "柳永词集")
    assert report["total_blocks"] == 9
    assert report["handled_blocks"] == 2
    assert report["excluded_blocks"] == 6
    assert report["untracked_blocks"] == 1
    assert report["untracked_sites"][0] == {
        "html": "x.html", "block": 5, "tag": "p",
        "classes": [], "anchor": None,
        "text_length": len("未被抽取的游离段落"),
    }
    assert "游离段落" not in str(report)
    assert report["exclusion_types"]["excluded_editorial_region"] == 2
    assert report["exclusion_types"]["excluded_editorial_heading"] == 2


def test_coverage_respects_scoped_ouyang_editorial_exception():
    book = Book({"x.html": (
        "<h2>西湖念语</h2><p>编者材料</p>"
        "<h2>采桑子</h2><p>合成正文</p>"
    )})
    sections = extract_sections(book, "x.html", "欧阳修词集")
    report = source_block_coverage(book, ["x.html"], sections, "欧阳修词集")
    assert report["total_blocks"] == 4
    assert report["handled_blocks"] == 2
    assert report["excluded_blocks"] == 2
    assert report["untracked_blocks"] == 0


def test_unknown_semantic_p_is_still_structurally_accounted_for():
    book = Book({"x.html": (
        "<h2>少年游</h2><p>词句</p><p>◆合成评论</p>"
        '<p class="kindle-cn-ref">待审引文</p>'
    )})
    sections = extract_sections(book, "x.html", "周邦彦词集")
    assert len(sections[0]["unknown"]) == 1
    report = source_block_coverage(book, ["x.html"], sections, "周邦彦词集")
    assert report["handled_blocks"] == report["total_blocks"] == 4
    assert report["untracked_blocks"] == 0


def test_report_surfaces_untracked_source_without_leaking_source_text():
    book = Book({"x.html": (
        "<p>用户不应看到的合成游离原文</p>"
        "<h2>清平乐</h2><p>合成词句</p>"
    )})
    toc = [{"title": "秦观词集", "children": [
        {"title": "清平乐", "href": "x.html"}]}]
    one = audit_collection(book, toc, "秦观词集", "秦观", "qin")
    assert one["source_coverage"]["untracked_blocks"] == 1
    md = render_md({"results": [one]})
    assert "未追踪源块" in md
    assert "`x.html` 块 1" in md
    assert "用户不应看到的合成游离原文" not in md


def test_unsupported_h4_outside_known_volume_is_untracked():
    book = Book({"x.html": (
        "<h2>采桑子</h2><p>词作</p>"
        "<h4>非纳兰附作标题</h4><p>下文</p>"
    )})
    section = extract_sections(book, "x.html", "秦观词集")
    report = source_block_coverage(book, ["x.html"], section, "秦观词集")
    assert report["untracked_blocks"] == 1
    assert report["untracked_sites"][0]["tag"] == "h4"
    assert report["handled_blocks"] == 3
