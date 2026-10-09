"""EPUB 结构报告与嵌套目录测试只使用合成元数据。"""

from pathlib import Path
from types import SimpleNamespace

from scripts.corpus.epub_import.epub import reader


def test_parse_toc_preserves_nested_groups_and_links():
    group = SimpleNamespace(title="卷一")
    first = SimpleNamespace(title="第一篇", href="part.xhtml#one")
    second = SimpleNamespace(title="第二篇", href="part.xhtml#two")

    assert reader.parse_toc([(group, [first, (group, [second])])]) == [
        {
            "title": "卷一",
            "children": [
                {"title": "第一篇", "href": "part.xhtml#one"},
                {
                    "title": "卷一",
                    "children": [
                        {"title": "第二篇", "href": "part.xhtml#two"},
                    ],
                },
            ],
        },
    ]


def test_inspect_epub_preserves_report_shape(monkeypatch):
    class FakeItem:
        def __init__(self, item_type, name):
            self.item_type = item_type
            self.name = name

        def get_type(self):
            return self.item_type

        def get_name(self):
            return self.name

    class FakeBook:
        toc = [SimpleNamespace(title="第一篇", href="text.xhtml#one")]

        def get_metadata(self, namespace, key):
            assert (namespace, key) == ("DC", "title")
            return [("测试书名", {})]

        def get_items(self):
            return [FakeItem(9, "text.xhtml"), FakeItem(1, "cover.jpg")]

    monkeypatch.setattr(reader.epub, "read_epub", lambda path: FakeBook())
    assert reader.inspect_epub(Path("test.epub")) == {
        "file": "test.epub",
        "metadata": {"title": "测试书名"},
        "summary": {"9": 1, "1": 1},
        "documents": ["text.xhtml"],
        "toc": [{"title": "第一篇", "href": "text.xhtml#one"}],
    }
