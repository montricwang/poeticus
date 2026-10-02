"""Synthetic EPUB fixtures only; no commercial source text in Git history."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/corpus/epub_import"))

from bs4 import BeautifulSoup
from extractor.blocks import iter_source_blocks
from extractor.extractor import extract_collection, extract_sections


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")


class Book:
    def __init__(self, items):
        self.items = items

    def get_item_with_href(self, name):
        return Item(self.items[name]) if name in self.items else None


def node(title, children=None, href=None):
    data = {"title": title}
    if children is not None:
        data["children"] = children
    if href is not None:
        data["href"] = href
    return data


def test_blocks_keep_inline_subtitle_linebreak_and_source():
    soup = BeautifulSoup(
        '<h2 id="a">调名<br/><span class="small" style="font-size:.8em">题名</span></h2>',
        "lxml",
    )
    block = list(iter_source_blocks(soup, "a.html"))[0]
    assert block.location()["block"] == 1
    assert block.location()["anchor"] == "a"
    assert [run["tag"] for run in block.runs] == ["text", "br", "span"]
    assert block.runs[-1]["style"] == "font-size:.8em"


def test_multi_author_toc_routes_and_resets_repeat():
    group = "温庭筠词集·韦庄词集"
    book = Book({
        "wen.html": "<h2>菩萨蛮</h2><p>甲词</p>",
        "wei.html": "<h2>又</h2><p>乙词</p><h2>浣溪沙</h2><p>丙词</p>"
    })
    toc = [node(group, [
        node("导读", href="guide.html"),
        node("温庭筠词集", [node("菩萨蛮", href="wen.html")]),
        node("韦庄词集", [node("又", href="wei.html")]),
        node("总评", href="review.html")
    ])]
    poems, files = extract_collection(book, toc, group, "wen-wei", "温庭筠")
    assert files == ["wen.html", "wei.html"]
    assert [p.author for p in poems] == ["温庭筠", "韦庄", "韦庄"]
    assert [p.tune for p in poems] == ["菩萨蛮", None, "浣溪沙"]
    assert any(w["type"] == "unresolved_tune_repeat" for w in poems[1].warnings)


def test_other_compound_volume_authors():
    group = "李煜词集（附：李璟词集 冯延巳词集）"
    toc = [node(group, [
        node("李煜词集", [node("调", href="a.html#one")]),
        node("李璟词集", [node("调", href="b.html#two")]),
        node("冯延巳词集", [node("调", href="c.html#three")])
    ])]
    book = Book({x: "<h2>浣溪沙</h2><p>正文</p>" for x in
                 ("a.html", "b.html", "c.html")})
    poems, _ = extract_collection(book, toc, group, "nantang", "李煜")
    assert [p.author for p in poems] == ["李煜", "李璟", "冯延巳"]


def test_notes_continue_only_with_same_direct_markup():
    book = Book({"x.html": (
        "<h2>词牌</h2><p>上片</p>"
        '<p class="review">◆评论第一段</p>'
        '<p class="review">评论续段</p>'
        '<p class="ref">其他资料独立段</p>'
    )})
    section = extract_sections(book, "x.html", "温庭筠词集")[0]
    assert section["text"] == ["上片"]
    assert section["commentaries"] == ["◆评论第一段\n评论续段"]
    assert any(w["type"] == "inferred_note_continuation"
               for w in section["warnings"])
    assert section["unknown"][0]["text"] == "其他资料独立段"
    assert any(w["type"] == "unclassified_after_notes"
               and w["text"] == "其他资料独立段"
               for w in section["warnings"])
    assert section["blocks"][-1]["block"] == 5


def test_caption_breaks_note_continuation():
    book = Book({"x.html": (
        "<h2>调</h2><p>词句</p><p>◆评论</p>"
        '<p class="kindle-cn-picture-txt-withfewcharactors">示意图</p>'
        "<p>可能的续段</p>"
    )})
    s = extract_sections(book, "x.html", "秦观词集")[0]
    assert s["text"] == ["词句"]
    assert s["commentaries"] == ["◆评论"]
    assert s["unknown"][0]["text"] == "可能的续段"
    assert any(x["role"] == "figure_caption" for x in s["blocks"])


def test_li_qingzhao_blank_poem_line_preserved():
    book = Book({"x.html": (
        '<h2>如梦令<br/><span class="kindle-cn-kkai">其二</span></h2>'
        '<p class="kindle-cn-poem-center">第一句，</p>'
        '<p class="kindle-cn-poem-center"></p>'
        '<p class="kindle-cn-poem-center">第二句。</p>'
        '<p>◎笺注</p>'
    )})
    s = extract_sections(book, "x.html", "李清照词集")[0]
    assert s["title"] == "其二"
    assert s["text"] == ["第一句，", "", "第二句。"]
    assert "stanza_separator" in [x["role"] for x in s["blocks"]]


def test_nalan_supplement_author_is_not_main_author():
    book = Book({"x.html": (
        "<h2>菩萨蛮</h2><p>纳兰词</p><p>◆评论</p>"
        '<p class="kindle-cn-para-left">【附】</p>'
        '<h4 class="kindle-cn-heading4"><span class="kindle-cn-bold">金缕曲</span>'
        '<span class="small">和容若韵</span></h4>'
        '<p class="kindle-cn-para-right">顾贞观</p>'
        "<p>顾氏词</p>"
        "<h2>又</h2><p>纳兰后续</p>"
    )})
    group = "纳兰词集"
    toc = [node(group, [node("卷一", [node("词", href="x.html")])])]
    poems, _ = extract_collection(book, toc, group, "nalan", "纳兰性德")
    assert [p.author for p in poems] == ["纳兰性德", "顾贞观", "纳兰性德"]
    assert [p.tune for p in poems] == ["菩萨蛮", "金缕曲", "菩萨蛮"]
    assert poems[1].title == "和容若韵"
    assert poems[1].content.text == ["顾氏词"]


def test_doubtful_section_is_tagged_in_warnings():
    group = "李清照词集"
    toc = [node(group, [node("存疑词作", [node("作品", href="d.html")])])]
    poems, _ = extract_collection(
        Book({"d.html": "<h2>一剪梅</h2><p>残句</p>"}),
        toc, group, "li-qingzhao", "李清照"
    )
    assert any(w["type"] == "doubtful_attribution" for w in poems[0].warnings)


def test_chronology_before_heading_never_leaks_into_poem():
    book = Book({"x.html": (
        '<p class="kindle-cn-para-no-indent1">淳熙某年（1186）</p>'
        "<h2>扬州慢</h2><p>词一</p>"
        '<p class="kindle-cn-para-no-indent1">某年（1191）</p>'
        "<h2>八归</h2><p>词二</p>"
    )})
    sections = extract_sections(book, "x.html", "姜夔词集")
    assert [s["text"] for s in sections] == [["词一"], ["词二"]]
    assert sections[1]["chronology"] == "某年（1191）"
    assert sections[0]["chronology"] == "淳熙某年（1186）"


def test_inline_body_style_warns_without_erasing_original_text():
    book = Book({"x.html": (
        "<h2>调</h2><p>上句<span style='font-size:.7em'>小注</span>下句</p>"
    )})
    s = extract_sections(book, "x.html", "贺铸词集")[0]
    assert s["text"] == ["上句小注下句"]
    assert any(w["type"] == "inline_body_style_review" for w in s["warnings"])


def test_unmarked_preverse_annotation_continuation_is_not_verse():
    book = Book({"x.html": (
        "<h2>浣溪沙</h2>"
        '<p class="note">◎材料第一段</p>'
        '<p class="note">材料第二段</p>'
        '<p class="verse">真正正文</p>'
    )})
    section = extract_sections(book, "x.html", "秦观词集")[0]
    assert section["annotations"] == ["◎材料第一段\n材料第二段"]
    assert section["text"] == []
    assert section["unknown"][0]["text"] == "真正正文"
    assert any(w["type"] == "unclassified_after_notes" for w in section["warnings"])


def test_reference_after_verse_requires_review_instead_of_becoming_verse():
    book = Book({"x.html": (
        "<h2>少年游</h2><p>真正正文</p>"
        '<p class="kindle-cn-ref">后附引证材料</p>'
    )})
    section = extract_sections(book, "x.html", "周邦彦词集")[0]
    assert section["text"] == ["真正正文"]
    assert section["unknown"][0]["text"] == "后附引证材料"
    assert any(w["type"] == "ambiguous_reference_after_verse"
               for w in section["warnings"])


def test_unsigned_inserted_work_has_no_fabricated_author_or_tune_inheritance():
    group = "纳兰词集"
    book = Book({"x.html": (
        "<h2>采桑子</h2><p>本集正文</p>"
        '<h4 class="kindle-cn-heading4">附作调名</h4><p>附作正文</p>'
        "<h2>又</h2><p>本集另一首</p>"
    )})
    toc = [node(group, [node("正文", href="x.html")])]
    poems, _ = extract_collection(book, toc, group, "nalan", "纳兰性德")
    assert [p.author for p in poems] == ["纳兰性德", "", "纳兰性德"]
    assert [p.tune for p in poems] == ["采桑子", "附作调名", "采桑子"]
    assert any(w["type"] == "missing_inserted_author" for w in poems[1].warnings)


def test_images_inside_heading_keep_original_character_order():
    book = Book({"x.html": (
        '<h2>临<img src="g1"/>江仙'
        '<span class="small">咏<img src="g2"/>梅</span></h2><p>正文</p>'
    )})
    section = extract_sections(book, "x.html", "辛弃疾词集")[0]
    assert section["tune"] == "临{{glyph:g1}}江仙"
    assert section["title"] == "咏{{glyph:g2}}梅"
    assert [w["src"] for w in section["warnings"] if w["type"] == "inline_image"] == ["g1", "g2"]


def test_missing_image_src_never_disappears_silently():
    book = Book({"x.html": "<h2>新调</h2><p>起句<img/>末句</p>"})
    section = extract_sections(book, "x.html", "柳永词集")[0]
    assert section["text"] == ["起句{{glyph:missing-src}}末句"]
    assert any(w["type"] == "missing_image_src" for w in section["warnings"])


def test_h1_author_change_within_one_shared_xhtml_is_respected():
    group = "温庭筠词集·韦庄词集"
    book = Book({"shared.html": (
        "<h1>温庭筠词集</h1><h2>菩萨蛮</h2><p>温词</p>"
        "<h1>韦庄词集</h1><h2>浣溪沙</h2><p>韦词</p>"
    )})
    toc = [node(group, [
        node("温庭筠词集", [node("甲", href="shared.html#wen")]),
        node("韦庄词集", [node("乙", href="shared.html#wei")]),
    ])]
    poems, files = extract_collection(book, toc, group, "both", "温庭筠")
    assert files == ["shared.html"]
    assert [p.author for p in poems] == ["温庭筠", "韦庄"]


def test_conflicting_toc_authorship_without_h1_does_not_guess():
    group = "温庭筠词集·韦庄词集"
    book = Book({"shared.html": "<h2>菩萨蛮</h2><p>一首正文</p>"})
    toc = [node(group, [
        node("温庭筠词集", [node("甲", href="shared.html#a")]),
        node("韦庄词集", [node("乙", href="shared.html#b")]),
    ])]
    poems, _ = extract_collection(book, toc, group, "both", "温庭筠")
    assert poems[0].author == ""
    assert any(w["type"] == "ambiguous_toc_attribution"
               for w in poems[0].warnings)


def test_inline_doubtful_heading_overrides_main_toc_zone():
    book = Book({"x.html": (
        "<h2>如梦令</h2><p>甲</p>"
        "<h1>存疑词作</h1><h2>蝶恋花</h2><p>乙</p>"
    )})
    toc = [node("李清照词集", [node("全卷", href="x.html")])]
    poems, _ = extract_collection(book, toc, "李清照词集", "li", "李清照")
    assert len(poems) == 2
    assert not any(w["type"] == "doubtful_attribution" for w in poems[0].warnings)
    assert any(w["type"] == "doubtful_attribution" for w in poems[1].warnings)


def test_h1_editorial_region_skips_internal_h2_until_next_work_region():
    group = "温庭筠词集·韦庄词集"
    book = Book({"one.html": (
        "<h1>导读</h1><h2>风格</h2><p>这不是作品。</p>"
        "<h1>温庭筠词集</h1><h2>菩萨蛮</h2><p>真正作品</p>"
    )})
    toc = [node(group, [node("全文", href="one.html")])]
    poems, _ = extract_collection(book, toc, group, "wen", "温庭筠")
    assert len(poems) == 1
    assert poems[0].tune == "菩萨蛮"
    assert poems[0].content.text == ["真正作品"]
