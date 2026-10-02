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
