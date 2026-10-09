"""用小型、可丢弃的本地资产测试 Serving 通道行为。"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.retrieval.serving_channels import SentenceBm25Channel
from scripts.retrieval.lexical_bm25 import build_bm25_index


def test_sentence_bm25_channel_recovers_work_and_handles_empty_terms(tmp_path) -> None:
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE VIRTUAL TABLE fts5_check USING fts5(text)")
    except sqlite3.OperationalError:
        pytest.skip("SQLite build does not include FTS5")

    works = [
        {
            "work_id": "w:1",
            "title": "赠别",
            "author": "杜牧",
            "dynasty": "唐",
            "content": "蜡烛有心还惜别。",
            "source": "test",
            "source_record_id": "one",
        },
        {
            "work_id": "w:2",
            "title": "杂诗",
            "author": "甲",
            "dynasty": "唐",
            "content": "山色入江流。",
            "source": "test",
            "source_record_id": "two",
        },
    ]
    chunks = [
        {
            "chunk_id": "w:1:sentence:0",
            "work_id": "w:1",
            "policy": "sentence",
            "chunk_index": 0,
            "start": 0,
            "end": 8,
            "text": "蜡烛有心还惜别。",
        },
        {
            "chunk_id": "w:2:sentence:0",
            "work_id": "w:2",
            "policy": "sentence",
            "chunk_index": 0,
            "start": 0,
            "end": 6,
            "text": "山色入江流。",
        },
    ]
    work_path = tmp_path / "works.jsonl"
    chunk_path = tmp_path / "chunks.jsonl"
    index_dir = tmp_path / "bm25"
    for path, rows in ((work_path, works), (chunk_path, chunks)):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    build_bm25_index(
        work_path=work_path,
        chunk_path=chunk_path,
        output_dir=index_dir,
        chunk_policy="sentence",
        expected_chunks=2,
    )
    channel = SentenceBm25Channel(index_dir)
    results = channel.search_many(["蜡烛有心", "。", "山色入江流"], top_k=5)

    assert len(results) == 3
    assert results[0][0].rank == 1
    assert results[0][0].work_id == "w:1"
    assert results[0][0].author == "杜牧"
    assert results[0][0].score_name == "bm25"
    assert results[1] == []
    assert results[2][0].work_id == "w:2"
    assert channel.profile()["queries"] == 3
