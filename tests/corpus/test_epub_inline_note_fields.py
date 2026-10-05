"""可逆 font1 行内注记测试只使用合成文本，不包含授权来源摘录。"""
from dataclasses import asdict

import pytest

from scripts.corpus.epub_import.extractor.extractor import (
    convert_to_poem,
    extract_sections,
)
from scripts.corpus.epub_import.pipeline.normalize import normalize_poem


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")


class Book:
    def __init__(self, items):
        self.items = items

    def get_item_with_href(self, name):
        return Item(self.items[name]) if name in self.items else None


def test_two_styled_annotations_retain_body_and_have_distinct_offsets():
    data = (
        "<h2>合成调</h2>"
        "<p>第一句<span class='font1'>附带说明甲</span>。"
        "第二句<span class='font1'>附带说明乙</span>。</p>"
    )
    s = extract_sections(Book({"x.html": data}), "x.html", "辛弃疾词集")[0]
    text = s["text"][0]
    assert text == "第一句附带说明甲。第二句附带说明乙。"
    assert [n["text"] for n in s["inline_notes"]] == [
        "附带说明甲", "附带说明乙",
    ]
    assert all(text[n["start"]:n["end"]] == n["text"]
               for n in s["inline_notes"])
    assert all(n["origin"] == "unverified" for n in s["inline_notes"])
    assert all(n["body_retains_note"] for n in s["inline_notes"])
    assert all(n["punctuation_outside_span"] for n in s["inline_notes"])
    assert all(n["boundary"] == "span_text_only" for n in s["inline_notes"])

    poem = convert_to_poem(s, 1, "test", "某人", "辛弃疾词集")
    data = asdict(poem)
    assert data["content"]["inline_notes"] == s["inline_notes"]


def test_quote_outside_span_is_explicitly_unresolved():
    html = (
        "<h2>合成调</h2>"
        "<p>正文甲<span class='font1'>某诗人写道：</span>"
        "“附带引文。”</p>"
    )
    s = extract_sections(Book({"x.html": html}), "x.html", "辛弃疾词集")[0]
    record = s["inline_notes"][0]
    assert record["text"] == "某诗人写道："
    assert record["boundary"] == "citation_continues_outside_span"
    assert s["text"] == ["正文甲某诗人写道：“附带引文。”"]
    assert any(w["type"] == "inline_note_boundary_review"
               for w in s["warnings"])


def test_confirmed_source_note_has_provenance_but_not_global_type_assumption():
    prefix = "<p>其他栏目</p>" * 133
    doc = (
        prefix
        + "<h2>西江月</h2>"
        + "<p>合成正文<span class='font1'>某人生日事</span>。</p>"
    )
    s = extract_sections(
        Book({"text00278.html": doc}), "text00278.html", "辛弃疾词集",
    )[0]
    n = s["inline_notes"][0]
    assert n["source_block"] == 135
    assert n["origin"] == "confirmed_author_in_reviewed_source"
    unrelated = extract_sections(
        Book({"unrelated.html": (
            "<h2>西江月</h2><p>正文<span class='font1'>另附说明</span>。</p>"
        )}), "unrelated.html", "辛弃疾词集"
    )[0]
    assert unrelated["inline_notes"][0]["origin"] == "unverified"


def test_repeated_text_or_images_inside_span_refuses_false_offsets():
    s = extract_sections(
        Book({"x.html": (
            "<h2>合成调</h2>"
            "<p>重字<span class='font1'>重字</span>句</p>"
        )}), "x.html", "辛弃疾词集",
    )[0]
    assert s["inline_notes"] == []
    assert any(w["type"] == "inline_note_offset_review"
               for w in s["warnings"])


def test_normalization_rebases_offsets_after_glyph_replacement():
    doc = (
        "<h2>合成调</h2>"
        '<p>开头<img src="glyph.png"/>正文'
        "<span class='font1'>合成说明</span>结尾</p>"
    )
    s = extract_sections(Book({"x.html": doc}), "x.html", "黄庭坚词集")[0]
    data = asdict(convert_to_poem(s, 1, "test", "某人", "黄庭坚词集"))
    before = data["content"]["inline_notes"][0]["start"]
    mapping = {"glyph.png": {"source_form": "辞"}}
    normalized = normalize_poem(data, mapping)
    after = normalized["content"]["inline_notes"][0]
    assert before > after["start"]
    assert normalized["content"]["text"] == ["开头辞正文合成说明结尾"]
    assert normalized["content"]["text"][0][after["start"]:after["end"]] == after["text"]

    # 已记录的 span 如果已不再匹配原始段落，绝不能静默变成
    # 挂到其他文字上的错误注记。
    after["start"] = 0
    with pytest.raises(ValueError, match="位置与原文不一致"):
        normalize_poem(normalized, mapping)


def test_kaiti_pagination_is_only_verse_not_inline_note():
    html = (
        "<h2>合成调</h2><p>合成上一句<a id='page14'></a>"
        "<span class='kaiti'>合成后一半</span></p>"
    )
    s = extract_sections(Book({"x.html": html}), "x.html", "纳兰词集")[0]
    assert s["inline_notes"] == []
    assert s["text"] == ["合成上一句合成后一半"]
