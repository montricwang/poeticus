import json
import sqlite3

import pytest

from backend.retrieval.metadata_store import (
    METADATA_SCHEMA_VERSION,
    MetadataStore,
    build_metadata_store,
    content_fingerprint,
)


def write_jsonl(path, rows):
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )


def test_metadata_store_builds_and_reads_rows(tmp_path):
    works = tmp_path / "works.jsonl"
    sentence = tmp_path / "sentence.jsonl"
    clause = tmp_path / "clause.jsonl"
    output = tmp_path / "metadata.sqlite3"

    write_jsonl(
        works,
        [
            {
                "work_id": "w1",
                "title": "甲",
                "author": "作者甲",
                "dynasty": "唐",
                "source_record_id": "s1",
                "content": "甲句。乙句。",
            },
            {
                "work_id": "w1-copy",
                "title": "甲别本",
                "author": "作者甲",
                "dynasty": "唐",
                "source_record_id": "s2",
                "content": "甲句。\n乙句。",
            },
            {
                "work_id": "w2",
                "title": "乙",
                "author": "作者乙",
                "dynasty": "宋",
                "source_record_id": "s3",
                "content": "丙句。",
            },
        ],
    )
    write_jsonl(
        sentence,
        [
            {
                "chunk_id": "s-0",
                "work_id": "w1",
                "text": "甲句。",
                "start": 0,
                "end": 3,
            },
            {
                "chunk_id": "s-1",
                "work_id": "w2",
                "text": "丙句。",
                "start": 0,
                "end": 3,
            },
        ],
    )
    write_jsonl(
        clause,
        [
            {
                "chunk_id": "c-0",
                "work_id": "w1",
                "text": "甲句",
                "start": 0,
                "end": 2,
            },
            {
                "chunk_id": "c-1",
                "work_id": "w1",
                "text": "乙句",
                "start": 3,
                "end": 5,
            },
        ],
    )

    result = build_metadata_store(
        work_path=works,
        sentence_chunk_path=sentence,
        clause_chunk_path=clause,
        output_path=output,
    )

    assert result["schema_version"] == METADATA_SCHEMA_VERSION
    assert result["works"] == 3
    assert result["sentence_chunks"] == 2
    assert result["clause_chunks"] == 2
    assert output.is_file()

    connection = sqlite3.connect(output)
    try:
        for table in ("sentence_chunks", "clause_chunks"):
            indexes = connection.execute(
                f"PRAGMA index_list({table})"
            ).fetchall()
            assert not any(row[2] for row in indexes)
    finally:
        connection.close()

    store = MetadataStore(output)
    assert store.stats()["schema_version"] == METADATA_SCHEMA_VERSION
    chunks = store.read_chunks("sentence", [1, 0])
    assert chunks[0].chunk_id == "s-0"
    assert chunks[1].work_id == "w2"

    clause_rows = store.read_chunks("clause", [1])
    assert clause_rows[1].text == "乙句"

    works_by_id = store.read_works(["w2", "w1"])
    assert works_by_id["w1"].author == "作者甲"
    assert works_by_id["w2"].dynasty == "宋"

    assert store.find_current_work_aliases(
        text="甲句。乙句。",
        author="作者甲",
    ) == {"w1", "w1-copy"}


def test_content_fingerprint_ignores_whitespace_only():
    assert content_fingerprint("甲句。\n乙句。") == content_fingerprint(
        "甲句。乙句。"
    )
    assert content_fingerprint("甲句，乙句。") != content_fingerprint(
        "甲句。乙句。"
    )



def test_metadata_store_rejects_stale_schema(tmp_path):
    output = tmp_path / "metadata-v1.sqlite3"
    connection = sqlite3.connect(output)
    try:
        connection.execute(
            "CREATE TABLE artifact_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO artifact_meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="schema version"):
        MetadataStore(output)
