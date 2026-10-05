"""用合成 XHTML 测试批量 EPUB 导入保护，不包含已出版诗词。"""
import json

import pytest

from scripts.corpus.epub_import.batch_import import (
    preflight_report,
    prepare_batch,
    run_batch,
)


class Item:
    def __init__(self, source):
        self.content = source.encode("utf-8")


class Book:
    def __init__(self, xhtml):
        self.xhtml = xhtml

    def get_item_with_href(self, filename):
        value = self.xhtml.get(filename)
        return Item(value) if value is not None else None


SPECS = [
    ("合成词集甲", "作者甲", "a"),
    ("合成词集乙", "作者乙", "b"),
]
TOC = [
    {"title": "合成词集甲", "children": [
        {"title": "正文", "href": "a.html"},
    ]},
    {"title": "合成词集乙", "children": [
        {"title": "正文", "href": "b.html"},
    ]},
]


def book_with_image_and_note():
    return Book({
        "a.html": (
            "<h2>采桑子</h2>"
            "<p>合成开头<img src='glyph.png'/>正文"
            "<span class='font1'>合成作者自注</span>。结句</p>"
        ),
        "b.html": (
            "<h2>浣溪沙</h2>"
            "<p>合成上片</p><p>合成下片</p>"
            "<p>◎合成文献注释</p>"
        ),
    })


def test_full_preflight_reports_missing_glyph_without_writing_licensed_json(tmp_path):
    paths = dict(
        specs=SPECS,
        map_dir=tmp_path / "maps",
        output_dir=tmp_path / "outputs",
        report_path=tmp_path / "reports" / "preflight.json",
    )
    report, outputs = run_batch(
        book_with_image_and_note(), TOC, check_only=True, **paths
    )
    assert outputs == []
    assert report["total_collections"] == 2
    assert report["total_candidate_poems"] == 2
    assert report["total_missing_glyph_sites"] == 1
    assert not report["ready_to_export"]
    assert report["collections"][0]["missing_glyphs"] == [
        {"html": "a.html", "src": "glyph.png"},
    ]
    assert not paths["output_dir"].exists()
    encoded = paths["report_path"].read_text(encoding="utf-8")
    assert "合成作者自注" not in encoded
    assert "合成开头" not in encoded
    with pytest.raises(RuntimeError, match="未写入任何正文"):
        run_batch(book_with_image_and_note(), TOC, **paths)
    assert not paths["output_dir"].exists()


def test_all_mode_exports_two_raw_normalized_and_one_combined_losslessly(tmp_path):
    map_dir = tmp_path / "maps"
    map_dir.mkdir()
    (map_dir / "a.json").write_text(
        json.dumps({"glyph.png": {"source_form": "葭"}}), encoding="utf-8"
    )
    out = tmp_path / "output"
    report, outputs = run_batch(
        book_with_image_and_note(), TOC,
        specs=SPECS, map_dir=map_dir, output_dir=out,
        report_path=tmp_path / "preflight.json",
    )
    assert report["ready_to_export"]
    assert report["total_missing_glyph_sites"] == 0
    assert report["collections"][0]["inline_note_candidates"] == 1
    assert len(outputs) == 6
    assert all((out / filename).exists() for filename in (
        "a.json", "a_normalized.json", "b.json",
        "b_normalized.json", "all_normalized.json", "all_manifest.json",
    ))
    raw = json.loads((out / "a.json").read_text(encoding="utf-8"))
    assert "{{glyph:glyph.png}}" in raw[0]["content"]["text"][0]
    together = json.loads(
        (out / "all_normalized.json").read_text(encoding="utf-8")
    )
    assert [p["id"] for p in together] == ["a-001", "b-001"]
    first = together[0]
    assert "葭" in first["content"]["text"][0]
    assert "{{glyph:" not in first["content"]["text"][0]
    note = first["content"]["inline_notes"][0]
    body = first["content"]["text"][note["paragraph_index"]]
    assert body[note["start"]:note["end"]] == note["text"]
    assert note["body_retains_note"] is True
    assert together[1]["content"]["annotations"] == ["◎合成文献注释"]
    manifest = json.loads(
        (out / "all_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["total"] == 2
    assert manifest["kind"] == "intermediate_poem_not_frontend"


def test_export_stops_on_unknown_content_even_if_no_glyphs(tmp_path):
    book = Book({
        "a.html": (
            "<h2>蝶恋花</h2><p>合成正文</p>"
            "<p>◆合成评论</p>"
            "<p class='other'>无法归类的合成段落</p>"
        ),
    })
    one = [("合成词集甲", "作者甲", "a")]
    plan = prepare_batch(book, TOC, specs=one, map_dir=tmp_path)
    result = preflight_report(plan)
    assert result["total_unexportable_issues"] == 1
    assert result["collections"][0]["unexportable"][0]["type"] == (
        "unclassified_after_notes"
    )
    assert "合成段落" not in json.dumps(result, ensure_ascii=False)
    with pytest.raises(RuntimeError, match="不能导出的未分类内容"):
        run_batch(
            book, TOC, specs=one, map_dir=tmp_path,
            output_dir=tmp_path / "out",
            report_path=tmp_path / "audit.json",
        )
    assert not (tmp_path / "out").exists()


def test_missing_image_src_is_explicitly_blocking(tmp_path):
    one = [("合成词集甲", "作者甲", "a")]
    book = Book({"a.html": "<h2>调</h2><p>甲<img/>乙</p>"})
    plan = prepare_batch(book, TOC, specs=one, map_dir=tmp_path)
    report = preflight_report(plan)
    assert not report["ready_to_export"]
    assert report["collections"][0]["unexportable"][0]["type"] == "missing_image_src"


def test_repeated_id_slugs_cannot_produce_ambiguous_combined_data(tmp_path):
    book = Book({
        "a.html": "<h2>词牌</h2><p>甲正文</p>",
        "b.html": "<h2>词牌</h2><p>乙正文</p>",
    })
    repeated_slug_specs = [
        ("合成词集甲", "作者甲", "same"),
        ("合成词集乙", "作者乙", "same"),
    ]
    with pytest.raises(RuntimeError, match="重复的作品 ID"):
        run_batch(
            book, TOC, specs=repeated_slug_specs,
            map_dir=tmp_path / "maps",
            output_dir=tmp_path / "out",
            report_path=tmp_path / "preflight.json",
        )
    assert not (tmp_path / "out").exists()
