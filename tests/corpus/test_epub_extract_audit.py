"""Audit reporting uses only small synthetic sources."""
from scripts.corpus.epub_import.analyze.audit_extraction import (
    audit_book, render_md, COLLECTIONS,
)


class Item:
    def __init__(self, content):
        self.content = content.encode("utf-8")


class Book:
    def get_item_with_href(self, href):
        if href == "a.html":
            return Item("<h2>蝶恋花</h2><p>甲。</p><p>◆评语</p>"
                        '<p class="other">需人工复核的另段</p>')
        return None


def test_audit_scoped_to_one_collection_with_provenance():
    toc = [{"title": "李清照词集", "children": [
        {"title": "作品", "href": "a.html#first"}]}]
    r = audit_book(Book(), toc, "李清照词集")
    assert len(r["results"]) == 1
    item = r["results"][0]
    assert item["candidate_poems"] == 1
    assert item["xhtml_count"] == 1
    assert item["warning_counts"]["unclassified_after_notes"] == 1
    assert item["review_items"][0]["source"]["html"] == "a.html"
    assert item["review_items"][0]["source"]["block"] == 1
    md = render_md(r)
    assert "未经文学校勘" in md
    assert "李清照词集" in md


def test_only_15_scoped_author_volumes_are_selected():
    assert len(COLLECTIONS) == 15
    assert "词品" not in {x[0] for x in COLLECTIONS}


def test_audit_reports_authorless_inserted_work():
    from scripts.corpus.epub_import.analyze.audit_extraction import audit_collection

    class InsertedBook:
        def get_item_with_href(self, href):
            if href == "a.html":
                return Item(
                    '<h4 class="kindle-cn-heading4">调名</h4><p>无署名附作</p>'
                )
            return None

    toc = [{"title": "纳兰词集", "children": [
        {"title": "作品", "href": "a.html"}]}]
    report = audit_collection(InsertedBook(), toc, "纳兰词集", "纳兰性德", "na")
    assert report["unassigned_author"] == 1
    assert report["warning_counts"]["missing_inserted_author"] == 1
    assert "作者待定" in render_md({"results": [report]})


def test_audit_prioritizes_unknown_author_and_reports_markup_not_text():
    from scripts.corpus.epub_import.analyze.audit_extraction import audit_collection

    class Volume:
        def get_item_with_href(self, href):
            if href == "x.html":
                return Item(
                    "<h2>采桑子</h2><p><span class='font1'>普通正文</span></p>"
                    '<h4 class="kindle-cn-heading4">小调</h4>'
                    "<p class='left'>模拟作品内容</p>"
                )
            return None

    toc = [{"title": "纳兰词集", "children": [{"title": "正文", "href": "x.html"}]}]
    result = audit_collection(Volume(), toc, "纳兰词集", "纳兰性德", "na")
    md = render_md({"results": [result]})
    assert "附词署名未识别" in md
    assert "left" in md
    assert "模拟作品内容" not in md
    assert result["unassigned_author"] == 1


def test_ambiguous_note_report_exposes_adjacent_markup_without_its_text():
    class Volume:
        def get_item_with_href(self, href):
            if href == "x.html":
                return Item(
                    '<h2>少年游</h2><p>正文</p>'
                    '<p class="comment">◆合成评论</p>'
                    '<p class="other">不应出现在Markdown中的合成待分类文字</p>'
                )
            return None
    toc = [{"title": "周邦彦词集", "children": [
        {"title": "少年游", "href": "x.html"}]}]
    from scripts.corpus.epub_import.analyze.audit_extraction import audit_collection
    one = audit_collection(Volume(), toc, "周邦彦词集", "周邦彦", "zhou")
    md = render_md({"results": [one]})
    assert "待分类块相邻结构" in md
    assert "commentaries/p/comment" in md
    assert "unknown/p/other" in md
    assert "合成待分类文字" not in md
    assert one["warning_counts"]["unclassified_after_notes"] == 1



def test_export_guard_blocks_unclassified_text_without_omitting_evidence():
    from types import SimpleNamespace
    import pytest
    from scripts.corpus.epub_import.import_poems import (
        ensure_no_unclassified_content,
    )
    candidate = SimpleNamespace(id="zhou-001", warnings=[
        {"type": "inline_image", "src": "glyph-1"},
        {"type": "unclassified_after_notes", "text": "合成待分类段落"},
    ])
    with pytest.raises(RuntimeError, match="zhou-001") as exc:
        ensure_no_unclassified_content([candidate])
    assert "禁止直接导出" in str(exc.value)
    assert "unclassified_after_notes" in str(exc.value)


def test_export_guard_allows_non_losing_warning_types_only():
    from types import SimpleNamespace
    from scripts.corpus.epub_import.import_poems import (
        ensure_no_unclassified_content,
    )
    candidates = [
        SimpleNamespace(id="x-001", warnings=[
            {"type": "inline_body_style_review"},
            {"type": "doubtful_attribution"},
            {"type": "inferred_note_continuation"},
        ]),
        SimpleNamespace(id="x-002", warnings=[]),
    ]
    assert ensure_no_unclassified_content(candidates) is None


def test_export_guard_blocks_pre_author_and_post_verse_unknown():
    from types import SimpleNamespace
    import pytest
    from scripts.corpus.epub_import.import_poems import (
        ensure_no_unclassified_content,
    )
    candidate = SimpleNamespace(id="na-001", warnings=[
        {"type": "unclassified_before_inserted_author", "text": "说明"}
    ])
    another = SimpleNamespace(id="x-003", warnings=[
        {"type": "ambiguous_reference_after_verse", "text": "引文"}
    ])
    with pytest.raises(RuntimeError) as exc:
        ensure_no_unclassified_content([candidate, another])
    assert "2 首" in str(exc.value)
    assert "unclassified_before_inserted_author" in str(exc.value)
    assert "ambiguous_reference_after_verse" in str(exc.value)
