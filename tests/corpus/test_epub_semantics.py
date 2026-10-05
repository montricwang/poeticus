"""只使用合成内容；不得提交商业选本正文。"""

import sys
from pathlib import Path
from types import ModuleType

try:
    import ebooklib  # noqa
except ImportError:
    lib = ModuleType("ebooklib")
    lib.epub = ModuleType("ebooklib.epub")
    sys.modules["ebooklib"] = lib
    sys.modules["ebooklib.epub"] = lib.epub

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "scripts/corpus/epub_import")
)
from extractor.extractor import extract_sections, extract_collection  # noqa
from pipeline.normalize import normalize_poem, unresolved_glyphs  # noqa


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")

    def get_content(self):
        return b"<html><body>SHOULD NOT APPEAR</body></html>"


class Book:
    def __init__(self, **html):
        self.data = html

    def get_item_with_href(self, name):
        return Item(self.data[name]) if name in self.data else None


def test_headings_tune_repetition_and_epub_anchor():
    book = Book(
        **{
            "part.html": """<h2 id="p1">采桑子</h2><p>正文甲</p>
        <h2 id="p2">又 <span class="font1">其二</span></h2><p>正文乙</p>"""
        }
    )
    toc = [
        {
            "title": "苏轼词集",
            "children": [
                {"title": "一", "href": "part.html#p1"},
                {"title": "二", "href": "part.html#p2"},
            ],
        }
    ]
    poems, files = extract_collection(book, toc, "苏轼词集", "su-shi", "苏轼")
    assert len(poems) == 2 and len(files) == 1
    assert [p.cipai for p in poems] == ["采桑子", "采桑子"]
    assert [p.title for p in poems] == [None, "其二"]
    assert not hasattr(poems[0], "title_raw")
    assert [p.content.text for p in poems] == [["正文甲"], ["正文乙"]]


def test_he_zhu_reversed_names_preserve_author_coined_yusheng():
    book = Book(
        **{
            "x.html": """<h2>横塘路<span style="font-size:.5em">青玉案</span></h2><p>词作甲</p>
        <h2>璧月堂<span style="font-size:.5em">小重山</span></h2><p>词作乙</p>"""
        }
    )
    s = extract_sections(book, "x.html", "贺铸词集")
    assert [(x["tune"], x["yusheng"], x["title"]) for x in s] == [
        ("青玉案", "横塘路", None),
        ("小重山", "璧月堂", None),
    ]


def test_liu_yong_separate_title_and_commentary():
    book = Book(
        **{
            "x.html": """<h2>木兰花</h2><p class="kindle-cn-para-center kindle-cn-kai">杏花</p>
        <p>上阕</p><p>下阕</p><p>◆评论</p><h2>又</h2>
        <p class="kindle-cn-para-center kindle-cn-kai">海棠</p><p>又一首</p>"""
        }
    )
    sections = extract_sections(book, "x.html", "柳永词集")
    assert [(x["tune"], x["title"]) for x in sections] == [
        ("木兰花", "杏花"),
        ("又", "海棠"),
    ]
    assert sections[0]["text"] == ["上阕", "下阕"]
    assert sections[0]["commentaries"] == ["◆评论"]


def test_preface_and_next_works_chronology_not_verse():
    book = Book(
        **{
            "j.html": """<h2>扬州慢</h2>
        <p class="kindle-cn-ref">这是一篇小序。</p><p>正文一</p><p>正文二</p>
        <p class="kindle-cn-para-no-indent1">某年丙申（1176）</p>
        <h2>八归<span class="kaiti">送故人</span></h2><p>正文三</p>"""
        }
    )
    sections = extract_sections(book, "j.html", "姜夔词集")
    assert sections[0]["prefaces"] == ["这是一篇小序。"]
    assert sections[0]["text"] == ["正文一", "正文二"]
    assert sections[1]["title"] == "送故人"
    assert sections[1]["text"] == ["正文三"]


def test_editorial_piece_is_not_a_poem():
    book = Book(
        **{
            "o.html": """<h2>西湖念语</h2><p>不是词</p><p>◎注</p>
        <h2>采桑子</h2><p>真正的词</p>"""
        }
    )
    sections = extract_sections(book, "o.html", "欧阳修词集")
    assert len(sections) == 1
    assert sections[0]["tune"] == "采桑子" and sections[0]["text"] == ["真正的词"]


def test_first_repeat_is_uncertain_not_misleading():
    book = Book(**{"x.html": "<h2>又</h2><p>正文</p>"})
    toc = [{"title": "苏轼词集", "children": [{"title": "一", "href": "x.html"}]}]
    poems, _ = extract_collection(book, toc, "苏轼词集", "s", "苏轼")
    assert poems[0].cipai is None
    assert poems[0].warnings[0]["type"] == "unresolved_tune_repeat"


def test_images_and_linebreaks_survive_and_normalize():
    book = Book(
        **{
            "x.html": """<h2>调名</h2><p>首句<img src="Image0001.jpg"/>末句<br/>第二行</p>
        <p class="kindle-cn-ref">不会成为小序，因为已有正文</p>"""
        }
    )
    sections = extract_sections(book, "x.html", "周邦彦词集")
    assert sections[0]["text"] == [
        "首句{{glyph:Image0001.jpg}}末句\n第二行",
    ]
    assert sections[0]["unknown"][0]["text"] == "不会成为小序，因为已有正文"
    assert any(w["type"] == "ambiguous_reference_after_verse"
               for w in sections[0]["warnings"])
    assert sections[0]["warnings"][0]["src"] == "Image0001.jpg"
    toc = [{"title": "周邦彦词集", "children": [{"title": "调名", "href": "x.html"}]}]
    poem, _ = extract_collection(book, toc, "周邦彦词集", "z", "周邦彦")
    from dataclasses import asdict

    sample = asdict(poem[0])
    sample["content"]["prefaces"] = ["序{{glyph:Image0001.jpg}}"]
    mapped = normalize_poem(
        sample, {"Image0001.jpg": {"source_form": "古", "display_form": "古"}}
    )
    assert mapped["content"]["text"][0] == "首句古末句\n第二行"
    assert mapped["content"]["prefaces"][0] == "序古"
    assert list(unresolved_glyphs([mapped])) == []


def test_heading_image_glyph_is_preserved_and_tracked():
    book = Book(
        **{
            "x.html": '<h2>虞美人<span class="small">赋荼</span><img src="Glyph.jpg"/></h2><p>花影</p>'
        }
    )
    sections = extract_sections(book, "x.html", "辛弃疾词集")
    assert sections[0]["title"] == "赋荼{{glyph:Glyph.jpg}}"
    assert sections[0]["warnings"][0]["category"] == "title"
    assert sections[0]["warnings"][0]["src"] == "Glyph.jpg"


def test_flatten_nested_volume_and_skip_front_matter():
    book = Book(
        **{
            "main.html": "<h2>词牌</h2><p>正文</p>",
            "guide.html": "<h2>导读段落</h2><p>不可导入</p>",
        }
    )
    toc = [
        {
            "title": "苏轼词集",
            "children": [
                {"title": "导读", "href": "guide.html"},
                {
                    "title": "卷一",
                    "children": [{"title": "词牌", "href": "main.html#a"}],
                },
                {"title": "总评", "href": "guide.html"},
            ],
        }
    ]
    poems, names = extract_collection(book, toc, "苏轼词集", "su", "苏轼")
    assert names == ["main.html"] and len(poems) == 1 and poems[0].cipai == "词牌"


def test_source_only_unicode_glyph_map_resolves():
    from pipeline.normalize import normalize_text

    assert (
        normalize_text("甲{{glyph:uni.png}}乙", {"uni.png": {"source_form": "龢"}})
        == "甲龢乙"
    )


def test_he_zhu_small_print_alternate_name_is_not_entire_tune():
    book = Book(
        **{
            "x.html": '<h2>新调名<span style="font-size:.5em">旧调，亦名另一调</span></h2><p>词作</p>'
        }
    )
    sections = extract_sections(book, "x.html", "贺铸词集")
    assert sections[0]["tune"] == "旧调"
    assert sections[0]["yusheng"] == "新调名"
    assert sections[0]["title"] is None
    # 当前导入器有意不引入 tune_alias 字段。
    assert "tune_alias" not in sections[0]
