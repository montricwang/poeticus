"""Synthetic contact-sheet / TSV glyph review tests, no commercial glyphs."""
import csv
import json

import pytest

from scripts.corpus.epub_import.review.review_glyphs import (
    apply_review,
    glyph_sites,
    prepare_review,
)


class Item:
    def __init__(self, data):
        self.content = data


class Book:
    def __init__(self, files):
        self.files = files

    def get_item_with_href(self, name):
        return Item(self.files[name]) if name in self.files else None


def example_report():
    return {
        "kind": "private-epub-import-preflight",
        "collections": [
            {"collection": "合成册甲", "slug": "demo-a", "missing_glyphs": [
                {"html": "x1.html", "src": "Image1.jpg"},
                {"html": "x2.html", "src": "Image1.jpg"},
                {"html": "x2.html", "src": "Image2.jpg"},
            ]},
            {"collection": "合成册乙", "slug": "demo-b", "missing_glyphs": [
                {"html": "x3.html", "src": "Image3.jpg"},
            ]},
        ],
    }


def test_contacts_deduplicate_references_and_tsv_contains_no_source_text(tmp_path):
    book = Book({
        "Image1.jpg": b"fake jpeg 1",
        "Image2.jpg": b"fake jpeg 2",
        "Image3.jpg": b"fake jpeg 3",
    })
    sheet = tmp_path / "review.html"
    tsv = tmp_path / "review.tsv"
    result = prepare_review(
        example_report(), book, sheet_path=sheet, tsv_path=tsv,
    )
    assert len(glyph_sites(example_report())) == 3
    assert result["unique_images"] == 3
    assert result["references"] == 4
    assert result["missing_assets"] == []
    markup = sheet.read_text(encoding="utf-8")
    assert "合成册甲" in markup
    assert "Image1.jpg" in markup
    assert "b'fake jpeg" not in markup
    assert (tmp_path / "review_images" / "001.jpg").read_bytes() == b"fake jpeg 1"
    with tsv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert [(r["slug"], r["src"]) for r in rows] == [
        ("demo-a", "Image1.jpg"), ("demo-a", "Image2.jpg"),
        ("demo-b", "Image3.jpg"),
    ]
    assert rows[0]["occurrences"] == "x1.html, x2.html"
    assert all(not row["source_form"] for row in rows)


def test_apply_review_requires_complete_mappings_and_supports_partial(tmp_path):
    report = example_report()
    sheet, tsv = tmp_path / "r.html", tmp_path / "r.tsv"
    prepare_review(report, Book({
        "Image1.jpg": b"1", "Image2.jpg": b"2", "Image3.jpg": b"3",
    }), sheet_path=sheet, tsv_path=tsv)
    with tsv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    rows[0]["source_form"] = "龢"
    rows[1]["source_form"] = "U+9FA5"
    rows[2]["source_form"] = "⿰木奇"
    rows[2]["display_form"] = "椅"
    with tsv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    folder = tmp_path / "maps"
    result = apply_review(tsv, map_dir=folder)
    assert result == {"mapped": 3, "unfilled": 0, "files_written": 2}
    a = json.loads((folder / "demo_a.json").read_text(encoding="utf-8"))
    b = json.loads((folder / "demo_b.json").read_text(encoding="utf-8"))
    assert a["Image1.jpg"]["source_form"] == "龢"
    assert a["Image2.jpg"]["source_form"] == "龥"
    assert b["Image3.jpg"]["display_form"] == "椅"

    # Existing data is protected against silent remapping.
    rows[0]["source_form"] = "和"
    with tsv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(RuntimeError, match="映射冲突"):
        apply_review(tsv, map_dir=folder)
    saved = json.loads((folder / "demo_a.json").read_text(encoding="utf-8"))
    assert saved["Image1.jpg"]["source_form"] == "龢"


def test_partial_save_and_preserve_existing_review_on_regeneration(tmp_path):
    book = Book({"Image1.jpg": b"1", "Image2.jpg": b"2", "Image3.jpg": b"3"})
    sheet, tsv = tmp_path / "r.html", tmp_path / "r.tsv"
    prepare_review(example_report(), book, sheet_path=sheet, tsv_path=tsv)
    with tsv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    rows[0]["source_form"] = "鸟"
    with tsv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(RuntimeError, match="未填写"):
        apply_review(tsv, map_dir=tmp_path / "maps")
    assert not (tmp_path / "maps").exists()
    partial = apply_review(tsv, map_dir=tmp_path / "maps", partial=True)
    assert partial["mapped"] == 1 and partial["unfilled"] == 2
    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        prepare_review(example_report(), book, sheet_path=sheet, tsv_path=tsv)


def test_image_href_collision_detected_instead_of_merging_different_bytes(tmp_path):
    one = {"collections": [{
        "collection": "合成甲", "slug": "a", "missing_glyphs": [
            {"html": "vol1/x.html", "src": "img.jpg"},
            {"html": "vol2/y.html", "src": "img.jpg"},
        ],
    }]}
    book = Book({"vol1/img.jpg": b"one", "vol2/img.jpg": b"two"})
    with pytest.raises(RuntimeError, match="不同图片"):
        prepare_review(
            one, book, sheet_path=tmp_path / "x.html",
            tsv_path=tmp_path / "x.tsv",
        )


def test_missing_source_image_reports_location_without_fake_character(tmp_path):
    report = {"collections": [{
        "collection": "甲", "slug": "a",
        "missing_glyphs": [{"html": "a.html", "src": "missing.jpg"}],
    }]}
    result = prepare_review(
        report, Book({}), sheet_path=tmp_path / "x.html",
        tsv_path=tmp_path / "x.tsv",
    )
    assert result["missing_assets"] == [("a", "missing.jpg")]
    assert "图片文件未找到" in (tmp_path / "x.html").read_text(encoding="utf-8")



def test_existing_tsv_flow_also_allows_ids_with_no_fabricated_display(tmp_path):
    report = {"collections": [{
        "collection": "合成册", "slug": "synthetic", "missing_glyphs": [
            {"html": "x.html", "src": "symbol.jpg"},
        ],
    }]}
    gallery, tsv = tmp_path / "gallery.html", tmp_path / "review.tsv"
    prepare_review(
        report, Book({"symbol.jpg": b"not-a-real-glyph"}),
        sheet_path=gallery, tsv_path=tsv,
    )
    with tsv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    rows[0]["source_form"] = "⿰木奇"
    with tsv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    result = apply_review(tsv, map_dir=tmp_path / "maps")
    assert result["mapped"] == 1
    entry = json.loads(
        (tmp_path / "maps" / "synthetic.json").read_text(encoding="utf-8")
    )["symbol.jpg"]
    assert entry["source_form"] == "⿰木奇"
    assert not entry["display_form"]
