"""Regression tests for He Zhu's three-part tune-heading convention.

All poetry below is artificial, including the example headings: no book
verses, modern annotations, or commercial EPUB pages are stored in Git.
"""
import json

from scripts.corpus.epub_import.batch_import import run_batch
from scripts.corpus.epub_import.extractor.extractor import extract_sections
from scripts.corpus.epub_import.pipeline.normalize import normalize_poem


class Item:
    def __init__(self, source):
        self.content = source.encode("utf-8")


class Book:
    def __init__(self, pages):
        self.pages = pages

    def get_item_with_href(self, href):
        value = self.pages.get(href)
        return Item(value) if value is not None else None


def test_he_zhu_three_part_heading_with_separate_spans():
    book = Book({"x.html": (
        "<h2>翦朝霞<span>思越人</span><span>牡丹</span></h2>"
        "<p>合成正文，仅作测试。</p>"
    )})
    [record] = extract_sections(book, "x.html", "贺铸词集")
    assert record["tune"] == "思越人"
    assert record["yusheng"] == "翦朝霞"
    assert record["title"] == "牡丹"
    assert not any(issue["type"] == "ambiguous_heading_parts"
                   for issue in record["warnings"])


def test_he_zhu_three_part_heading_with_fullwidth_space_inside_single_run():
    book = Book({"x.html": (
        "<h2>翦朝霞<span>思越人　牡丹</span></h2>"
        "<p>合成正文。</p>"
    )})
    [record] = extract_sections(book, "x.html", "贺铸词集")
    assert (record["tune"], record["yusheng"], record["title"]) == (
        "思越人", "翦朝霞", "牡丹"
    )


def test_he_zhu_yusheng_with_alias_note_does_not_create_cipai_alias():
    book = Book({"x.html": (
        "<h2>半死桐<span>思越人，亦名鹧鸪天</span></h2>"
        "<p>合成正文。</p>"
    )})
    [record] = extract_sections(book, "x.html", "贺铸词集")
    assert record["tune"] == "思越人"
    assert record["yusheng"] == "半死桐"
    assert record["title"] is None
    assert "cipai_alias" not in record


def test_non_he_zhu_never_gets_yusheng_even_with_three_heading_parts():
    book = Book({"x.html": (
        "<h2>水调歌头<span>其一</span><span>续记</span></h2>"
        "<p>合成正文。</p>"
    )})
    [record] = extract_sections(book, "x.html", "苏轼词集")
    assert record["tune"] == "水调歌头"
    assert record["yusheng"] is None
    assert record["title"] == "其一\n续记"
    assert any(issue["type"] == "ambiguous_heading_parts"
               for issue in record["warnings"])


def test_yusheng_image_glyph_is_normalized_and_audited():
    book = Book({"x.html": (
        "<h2>翦<img src='rare.jpg'/>霞<span>思越人　牡丹</span></h2>"
        "<p>合成正文。</p>"
    )})
    [record] = extract_sections(book, "x.html", "贺铸词集")
    assert record["yusheng"] == "翦{{glyph:rare.jpg}}霞"
    assert record["tune"] == "思越人"
    assert record["title"] == "牡丹"
    assert record["warnings"][0]["category"] == "yusheng"

    from scripts.corpus.epub_import.extractor.extractor import convert_to_poem
    from dataclasses import asdict
    poem = asdict(convert_to_poem(record, 1, "he-zhu", "贺铸", "贺铸词集"))
    output = normalize_poem(poem, {"rare.jpg": {"source_form": "𠂉"}})
    assert output["yusheng_title"] == "翦𠂉霞"
    assert output["warnings"][0]["status"] == "resolved"
    assert output["warnings"][0]["resolved_form"] == "𠂉"


def test_batch_reexport_preserves_yusheng_as_optional_field(tmp_path):
    book = Book({"he.html": (
        "<h2>翦朝霞<span>思越人　牡丹</span></h2>"
        "<p>合成正文。</p>"
    ), "normal.html": (
        "<h2>菩萨蛮</h2><p>合成正文。</p>"
    )})
    toc = [
        {"title": "贺铸词集", "children": [
            {"title": "正文", "href": "he.html"},
        ]},
        {"title": "温庭筠词集", "children": [
            {"title": "正文", "href": "normal.html"},
        ]},
    ]
    report, _ = run_batch(
        book, toc, specs=[
            ("贺铸词集", "贺铸", "he-zhu"),
            ("温庭筠词集", "温庭筠", "wen"),
        ],
        map_dir=tmp_path / "maps",
        output_dir=tmp_path / "out",
        report_path=tmp_path / "preflight.json",
    )
    assert report["ready_to_export"]
    poems = json.loads((tmp_path / "out" / "all_normalized.json").read_text(
        encoding="utf-8"
    ))
    assert [(x["cipai"], x["yusheng_title"], x["title"]) for x in poems] == [
        ("思越人", "翦朝霞", "牡丹"),
        ("菩萨蛮", None, None),
    ]
    assert len(poems) == 2
    assert all("tune" not in poem and "yusheng" not in poem for poem in poems)
