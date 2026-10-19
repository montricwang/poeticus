"""Document Corpus 原始 EPUB → 文献节点 → Chunk 的无数据库回归。"""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.corpus.document_db import (
    BOOKS,
    RAW_ROOT,
    digest,
    node_rows,
    prepare,
    read_epub_sections,
    uid,
)


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    return prepare()


def test_all_four_epubs_regenerate_exact_corpus(corpus: list[dict]) -> None:
    assert {b["title"] for b in corpus} == set(BOOKS)
    assert {b["title"]: len(b["sections"]) for b in corpus} == {
        "人間詞話": 148,
        "樂府指迷": 34,
        "白雨齋詞話": 669,
        "碧雞漫志": 65,
    }
    assert len({(b["title"], s["file"], s["section_id"])
                for b in corpus for s in b["sections"]}) == 916


def test_hierarchy_and_chunks_preserve_parent_and_text(corpus: list[dict]) -> None:
    nodes = []
    chunks = []
    for book in corpus:
        tree, leaves = node_rows(book)
        nodes.extend(tree)
        chunks.extend(leaves)
        index = {n["id"]: n for n in tree}
        assert len(index) == len(tree)
        assert len({n["source_key"] for n in tree}) == len(tree)
        for n in tree:
            if n["parent_id"] is not None:
                assert n["parent_id"] in index
                assert index[n["parent_id"]]["sort_order"] < n["sort_order"]
        for leaf in leaves:
            node = index[leaf["node_id"]]
            assert node["node_type"] == "section"
            assert node["body_text"] and leaf["text"] == f"{node['title']} {node['body_text']}"
            assert leaf["end_offset"] == len(leaf["text"])
            assert leaf["text_sha256"] == digest(leaf["text"])
            assert node["source_locator"]["heading_id"]
    assert len(nodes) == 938
    assert len(chunks) == 916


def test_evidence_source_anchor_and_structure(corpus: list[dict]) -> None:
    book = next(b for b in corpus if b["title"] == "人間詞話")
    tree, chunks = node_rows(book)
    node = next(n for n in tree if "有我之境" in n["title"])
    parents = {n["id"]: n for n in tree}
    assert parents[node["parent_id"]]["title"] == "卷上 已刊部分"
    assert parents[parents[node["parent_id"]]["parent_id"]]["title"] == "正文"
    assert node["source_locator"]["heading_id"]
    assert node["source_locator"]["epub_file"].endswith(".xhtml")
    assert len([c for c in chunks if c["node_id"] == node["id"]]) == 1


def test_epub_drift_detected_without_modifying_original(corpus: list[dict]) -> None:
    book = next(b for b in corpus if b["title"] == "樂府指迷")
    broken = deepcopy(book["sections"][0])
    broken["text"] = "不是真正的底本"
    with pytest.raises(ValueError, match="与旧语料不一致"):
        read_epub_sections(RAW_ROOT / "樂府指迷.epub", [broken])
    broken["text"] = book["sections"][0]["text"]
    broken["heading_id"] = "nonexistent"
    with pytest.raises(ValueError, match="与旧语料不一致"):
        read_epub_sections(RAW_ROOT / "樂府指迷.epub", [broken])


def test_version_identity_is_source_specific(corpus: list[dict]) -> None:
    source = corpus[0]
    doc_id = uid("document:" + source["title"])
    version1 = uid(f"version:{doc_id}:{source['source_sha256']}")
    version2 = uid(f"version:{doc_id}:{'f' * 64}")
    assert version1 != version2
