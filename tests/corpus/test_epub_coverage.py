"""来源块覆盖测试只使用合成数据，不包含受版权保护的 EPUB 段落。"""
from pydantic import TypeAdapter

from scripts.corpus.epub_import.diagnostics.coverage import CoverageReport, source_block_coverage
from scripts.corpus.epub_import.diagnostics.audit_extraction import audit_collection, render_md
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
    covered = TypeAdapter(CoverageReport).validate_python(one["source_coverage"])
    assert covered["untracked_blocks"] == 1
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



def test_unscanned_div_and_list_item_text_is_inventoried_without_content():
    book = Book({"x.html": (
        "<h2>如梦令</h2><p>词正文</p>"
        "<div class='aside'>游离编者材料</div>"
        "<ul><li>无法归类的条目</li></ul>"
        "<div><span>附加杂项文字</span></div>"
        "<!--这个源代码注释不应进入报告-->"
    )})
    sections = extract_sections(book, "x.html", "李清照词集")
    report = source_block_coverage(book, ["x.html"], sections, "李清照词集")
    assert report["untracked_blocks"] == 0
    assert report["unsupported_text_nodes"] == 3
    assert [s["parent_tag"] for s in report["unsupported_text_sites"]] == [
        "div", "li", "span"
    ]
    assert "游离编者材料" not in str(report)
    assert "无法归类的条目" not in str(report)


def test_bold_and_emphasis_inside_handled_paragraph_are_not_double_counted():
    book = Book({"x.html": (
        "<h2>清平乐</h2><p><b>强调的词句</b><em>另一部分</em></p>"
    )})
    sections = extract_sections(book, "x.html", "秦观词集")
    report = source_block_coverage(book, ["x.html"], sections, "秦观词集")
    assert report["handled_blocks"] == 2
    assert report["unsupported_text_nodes"] == 0



def test_chronology_labels_are_not_mislabeled_as_missing_or_fully_exported():
    """第一个 h2 之前的年代标记应作为中间上下文保留。"""
    book = Book({"x.html": (
        "<h1>姜夔词集</h1>"
        '<p class="kindle-cn-para-no-indent1">绍熙某年（1191）</p>'
        "<h2>扬州慢</h2><p>模拟词句甲</p>"
        '<p class="kindle-cn-para-no-indent1">庆元某年（1196）</p>'
        "<h2>暗香</h2><p>模拟词句乙</p>"
    )})
    sections = extract_sections(book, "x.html", "姜夔词集")
    assert [s["chronology"] for s in sections] == [
        "绍熙某年（1191）", "庆元某年（1196）"
    ]
    coverage = source_block_coverage(
        book, ["x.html"], sections, "姜夔词集"
    )
    assert coverage["total_blocks"] == 7
    assert coverage["handled_blocks"] == 4
    assert coverage["excluded_blocks"] == 1
    assert coverage["untracked_blocks"] == 0
    assert coverage["internal_chronology_not_exported"] == 2
    assert [s["block"] for s in coverage["chronology_sites"]] == [2, 5]
    assert "绍熙" not in str(coverage)

    toc = [{"title": "姜夔词集", "children": [
        {"title": "正文", "href": "x.html"}]}]
    report = audit_collection(book, toc, "姜夔词集", "姜夔", "jiang")
    md = render_md({"results": [report]})
    assert "年代标记（只用于临时章节上下文" in md
    assert "未写入最终 Poem" in md
    assert "绍熙" not in md


def test_same_css_without_date_does_not_disappear_as_chronology():
    book = Book({"x.html": (
        '<p class="kindle-cn-para-no-indent1">非年代说明文字</p>'
        "<h2>忆王孙</h2><p>模拟词句</p>"
    )})
    sections = extract_sections(book, "x.html", "姜夔词集")
    coverage = source_block_coverage(
        book, ["x.html"], sections, "姜夔词集"
    )
    assert coverage["internal_chronology_not_exported"] == 0
    assert coverage["untracked_blocks"] == 1
    assert coverage["untracked_sites"][0]["block"] == 1
