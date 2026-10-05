"""行内标记证据覆盖测试只使用合成数据，Git 中不包含已出版诗词。"""
from scripts.corpus.epub_import.diagnostics.audit_inline_styles import (
    collect_inline_evidence,
    render_md,
)


class Item:
    def __init__(self, markup):
        self.content = markup.encode("utf-8")


class Book:
    def __init__(self, files):
        self.files = files

    def get_item_with_href(self, name):
        return Item(self.files[name]) if name in self.files else None


NAME = "李煜词集（附：李璟词集 冯延巳词集）"
SPECS = [(NAME, "李煜", "nantang")]
TOC = [{"title": NAME, "children": [{"title": "词集", "href": "x.html"}]}]


def test_diagnostic_distinguishes_styled_marker_plain_marker_and_unrelated_styles():
    book = Book({"x.html": (
        "<h2>谢新恩</h2>"
        "<p>甲<span style='font-size:smaller'>（以下缺）</span>乙</p>"
        "<h2>新调</h2>"
        "<p>（以下缺）甲<span class='small'>普通有样式词句</span>乙</p>"
        "<h2>又调</h2><p>甲（以下缺）乙</p>"
        "<h2>第四调</h2>"
        "<p><span style='color:red'>原词（以下缺）</span></p>"
        "<h2>第五调</h2>"
        "<p>开头<span style='font-size:smaller'>另一处特殊字体</span>结尾</p>"
    )})
    report = collect_inline_evidence(book, TOC, SPECS)
    assert report["total_text_blocks"] == 5
    assert report["warned_blocks"] == 3
    assert report["gap_marker_blocks"] == 4
    assert report["gap_marker_warned_blocks"] == 2
    assert report["gap_marker_inside_styled_span_blocks"] == 2

    sites = report["sites"]
    assert [s["block"] for s in sites] == [2, 4, 6, 8, 10]
    assert [(s["warned"], s["has_gap_marker"],
             s["gap_inside_styled_span"]) for s in sites] == [
        (True, True, True),
        (True, True, False),
        (False, True, False),
        (False, True, True),
        (True, False, False),
    ]
    assert "span class=- style=font-size:smaller" in report["style_counts"]


def test_shareable_md_contains_only_locations_and_style_structure():
    book = Book({"x.html": (
        "<h2>新调</h2>"
        "<p>版权限制示例甲<span class='small'>（以下缺）</span>版权限制示例乙</p>"
    )})
    report = collect_inline_evidence(book, TOC, SPECS)
    md = render_md(report)
    assert "x.html" in md
    assert "特殊字体告警源块：1" in md
    assert "包含“（以下缺）”形式的源块：1" in md
    assert "span class=small" in md
    assert "版权限制示例甲" not in md
    assert "版权限制示例乙" not in md
    assert "标记整体位于带样式 span" in md
    assert "这里" in md
