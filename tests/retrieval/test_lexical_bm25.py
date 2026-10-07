import json
import sqlite3

import pytest

from scripts.retrieval.lexical_bm25 import (
    build_bm25_index,
    build_match_query,
    character_ngrams,
    search_bm25,
)


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _work(record_id, *, title, author, dynasty):
    return {
        "work_id": f"w:{record_id}",
        "title": title,
        "author": author,
        "dynasty": dynasty,
        "content": "",
        "source": "test",
        "source_record_id": record_id,
    }


def _chunk(record_id, work_id, text, index=0):
    return {
        "chunk_id": f"{work_id}:sentence:{index}",
        "work_id": work_id,
        "policy": "sentence",
        "chunk_index": index,
        "start": 0,
        "end": len(text),
        "text": text,
    }


def test_character_ngrams_respect_punctuation_boundaries():
    grams = character_ngrams("片片轻鸥，落晚沙。", min_n=2, max_n=3)

    assert grams == [
        "片片",
        "片轻",
        "轻鸥",
        "片片轻",
        "片轻鸥",
        "落晚",
        "晚沙",
        "落晚沙",
    ]
    assert "鸥落" not in grams


def test_build_match_query_deduplicates_terms():
    query = build_match_query("片片片", min_n=2, max_n=2)

    assert query == '"片片"'


def test_build_and_search_bm25_with_chronology_filter(tmp_path):
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE fts5_check USING fts5(text)")
        connection.close()
    except sqlite3.OperationalError:
        pytest.skip("SQLite build does not include FTS5")

    works = [
        _work("1", title="赠别", author="杜牧", dynasty="唐"),
        _work("2", title="杂诗", author="甲", dynasty="唐"),
        _work("3", title="后作", author="乙", dynasty="宋"),
    ]
    chunks = [
        _chunk(
            "1",
            "w:1",
            "蜡烛有心还惜别，替人垂泪到天明。",
        ),
        _chunk("2", "w:2", "山色入江流。"),
        _chunk("3", "w:3", "蜡烛到明垂泪。"),
    ]
    work_path = tmp_path / "works.jsonl"
    chunk_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "bm25"
    _write_jsonl(work_path, works)
    _write_jsonl(chunk_path, chunks)

    manifest = build_bm25_index(
        work_path=work_path,
        chunk_path=chunk_path,
        output_dir=output_dir,
        chunk_policy="sentence",
        expected_chunks=3,
    )
    result = search_bm25(
        query="蜡烛到明垂泪",
        index_dir=output_dir,
        before_dynasty="宋",
        probe_text="替人垂泪到天明",
        probe_author="杜牧",
    )

    assert manifest["chunks"] == 3
    assert manifest["term_representation"] == "character_ngram"
    assert result["ranking"][0]["work"]["author"] == "杜牧"
    assert all(row["work"]["dynasty"] != "宋" for row in result["ranking"])
    assert result["probes"][0]["rank"] == 1



def test_sample_build_only_keeps_referenced_works(tmp_path):
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE fts5_check USING fts5(text)")
        connection.close()
    except sqlite3.OperationalError:
        pytest.skip("SQLite build does not include FTS5")

    works = [
        _work("1", title="一", author="甲", dynasty="唐"),
        _work("2", title="二", author="乙", dynasty="唐"),
        _work("3", title="三", author="丙", dynasty="唐"),
    ]
    chunks = [
        _chunk("1", "w:1", "片片轻鸥落晚沙。"),
        _chunk("2", "w:2", "春水碧于天。"),
        _chunk("3", "w:3", "画船听雨眠。"),
    ]
    work_path = tmp_path / "works.jsonl"
    chunk_path = tmp_path / "chunks.jsonl"
    output_dir = tmp_path / "sample"
    _write_jsonl(work_path, works)
    _write_jsonl(chunk_path, chunks)

    manifest = build_bm25_index(
        work_path=work_path,
        chunk_path=chunk_path,
        output_dir=output_dir,
        chunk_policy="sentence",
        expected_chunks=1,
        max_chunks=1,
    )

    connection = sqlite3.connect(output_dir / "index.sqlite3")
    try:
        stored_works = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        stored_chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        connection.close()

    assert manifest["works"] == 1
    assert manifest["chunks"] == 1
    assert manifest["sampled_chunks_seen"] == 1
    assert manifest["database_bytes"] > 0
    assert manifest["build_elapsed_seconds"] >= 0
    assert stored_works == 1
    assert stored_chunks == 1
