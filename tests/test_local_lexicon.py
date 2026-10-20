"""离线测试词典递归展开、别名、校验和及 SQLite 索引。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.corpus.local_lexicon import (
    TITLE, all_needed, catalog_from_index, children_from_text,
    load_page, plain_wikitext, rebuild, render_entry, save_page,
)


def _source(root: Path, title: str, content: str, revision: int = 123) -> None:
    page = {
        "title": title,
        "pageid": revision,
        "revisions": [{
            "revid": revision,
            "timestamp": "2024-05-23T12:05:12Z",
            "slots": {"main": {"content": content}},
        }],
    }
    assert save_page(root, page)


def test_catalog_extracts_variants_and_volume() -> None:
    index = (
        "==目次==\n===卷一===\n"
        "*[[詩詞曲語辭匯釋/遮莫|遮莫]]（五條）　"
        '<span class="小字s">折莫　折末　者莫</span>\n'
        "===卷二===\n*[[詩詞曲語辭匯釋/怎生|怎生]]\n"
    )
    results = catalog_from_index(index)
    assert [r["headword"] for r in results] == ["遮莫", "怎生"]
    assert results[0]["variants"] == ["折莫", "折末", "者莫"]
    assert results[0]["volume"] == "卷一"
    assert results[1]["volume"] == "卷二"


def test_transclusion_follows_original_order_and_keeps_source(tmp_path: Path) -> None:
    word = TITLE + "/遮莫"
    part1, part2 = word + "/（一）", word + "/（二）"
    _source(tmp_path, TITLE, "*[[詩詞曲語辭匯釋/遮莫|遮莫]]\n")
    _source(tmp_path, word,
            "{{:" + part1 + "}}\n\n{{:" + part2 + "}}\n\np.135\n"
            "<noinclude>{{header|private}}</noinclude>")
    _source(tmp_path, part1, "===[[白話詞彙/遮莫|遮莫]]===\n\n'''遮莫'''，儘教之義。")
    _source(tmp_path, part2, "==遮莫（二）==\n\n第二義：無妨。")
    word_page = load_page(tmp_path, word)
    main_page = load_page(tmp_path, TITLE)
    assert word_page is not None and main_page is not None
    assert children_from_text(word_page["wikitext"]) == [part1, part2]
    assert all_needed(tmp_path, catalog_from_index(main_page["wikitext"])) == [
        TITLE, word, part1, part2
    ]
    text, ok = render_entry(tmp_path, word)
    assert ok
    assert "遮莫，儘教之義。" in text
    assert "第二義：無妨。" in text
    assert text.index("儘教之義") < text.index("第二義") < text.index("p.135")
    assert "header|private" not in text
    part_page = load_page(tmp_path, part1)
    assert part_page is not None
    assert part_page["revision_id"] == 123
    assert len(part_page["sha256"]) == 64
    rebuild(tmp_path)
    import sqlite3

    db = sqlite3.connect(tmp_path / "lexicon.sqlite")
    try:
        row = db.execute("SELECT headword,complete,full_text FROM entry").fetchone()
        assert row[0] == "遮莫" and row[1] == 1
        assert "第二義：無妨" in row[2]
    finally:
        db.close()


def test_missing_child_is_incomplete_and_tamper_is_detected(tmp_path: Path) -> None:
    word = TITLE + "/遮莫"
    part = word + "/（一）"
    _source(tmp_path, word, "{{:" + part + "}}\np.135")
    text, ok = render_entry(tmp_path, word)
    assert not ok and text.endswith("p.135")
    path = next((tmp_path / "sources").glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["wikitext"] = "tampered"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_page(tmp_path, word)


def test_render_traditional_and_rich_text() -> None:
    wikitext = "===[[白話詞彙/怎生|怎生]]===\n<span class=\"專名\">張生</span>說：'''怎生'''？"
    assert plain_wikitext(wikitext) == "怎生\n\n張生說：怎生？"
