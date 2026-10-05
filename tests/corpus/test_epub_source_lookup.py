"""本地诊断测试只使用合成数据，绝不保存授权来源摘录。"""
import pytest

from scripts.corpus.epub_import.diagnostics.inspect_source import inspect_source


class Item:
    def __init__(self, html):
        self.content = html.encode("utf-8")


class Book:
    def __init__(self, sources):
        self.sources = sources

    def get_item_with_href(self, name):
        return Item(self.sources[name]) if name in self.sources else None


def test_two_chronology_targets_show_original_and_context_and_role():
    book = Book({"x.html": (
        "<h1>姜夔词集</h1>"
        '<p class="kindle-cn-para-no-indent1">某年（1191）</p>'
        "<h2>扬州慢</h2><p>合成正文甲</p>"
        '<p class="kindle-cn-para-no-indent1">某年（1196）</p>'
        "<h2>暗香</h2><p>合成正文乙</p>"
    )})
    report = inspect_source(
        book, "x.html", [2, 5], collection="姜夔词集",
        before=1, after=1,
    )
    assert "目标块 2" in report
    assert "目标块 5" in report
    assert "年代标记（抽取器仅暂存，不导出 Poem）" in report
    assert "某年（1191）" in report
    assert "某年（1196）" in report
    assert "所在候选词牌：扬州慢" in report
    assert "kindle-cn-para-no-indent1" in report


def test_find_locates_matching_block_and_keeps_source_number():
    book = Book({"x.html": (
        "<h2>如梦令</h2><p>上片</p><p>需要检查的文字</p><p>下片</p>"
    )})
    report = inspect_source(
        book, "x.html", [], find=["检查的"], before=1, after=1,
    )
    assert "目标块 3" in report
    assert "目标：3" in report
    assert "上片" in report
    assert "下片" in report


def test_raw_xhtml_opt_in_and_long_text_default_truncated():
    book = Book({"x.html": (
        "<h2>新调</h2><p><span class='small'>"
        + "合成文字" * 100 + "</span></p>"
    )})
    short = inspect_source(
        book, "x.html", [2], before=0, after=0, max_chars=12
    )
    assert "展开原始 XHTML" not in short
    assert "用 --full 查看" in short
    assert "合成文字" * 30 not in short
    full = inspect_source(
        book, "x.html", [2], before=0, after=0,
        max_chars=1000, show_html=True,
    )
    assert "<details><summary>展开原始 XHTML" in full
    assert "§" not in full
    assert "§§§" not in full
    assert "<span class=\"small\">" in full
    assert "合成文字" * 30 in full


def test_role_does_not_claim_a_chronology_was_exported():
    book = Book({"x.html": (
        '<p class="kindle-cn-para-no-indent1">某年（1191）</p>'
        "<h2>扬州慢</h2><p>合成正文</p>"
    )})
    report = inspect_source(
        book, "x.html", [1, 2, 3], collection="姜夔词集",
        before=0, after=0,
    )
    assert "年代标记（抽取器仅暂存，不导出 Poem）" in report
    assert "抽取角色：work_start" in report
    assert "抽取角色：text" in report


def test_lookup_rejects_missing_or_invalid_blocks_and_no_matches():
    book = Book({"x.html": "<h2>浣溪沙</h2><p>正文</p>"})
    with pytest.raises(ValueError, match="XHTML 不存在"):
        inspect_source(book, "missing.html", [1])
    with pytest.raises(ValueError, match="不包含这些块号"):
        inspect_source(book, "x.html", [3])
    with pytest.raises(ValueError, match="没有匹配段落"):
        inspect_source(book, "x.html", [], find=["不存在"])
    with pytest.raises(ValueError, match="超过 40"):
        inspect_source(
            Book({"x.html": "<p>某句</p>" * 45}), "x.html", [],
            find=["某句"]
        )
