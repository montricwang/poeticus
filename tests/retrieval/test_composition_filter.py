"""Poem Retrieval 组诗去重：关系表、当前正文命中、共召回及补位。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.retrieval.poem.composition_filter import (
    WorkCompositionLookup,
    filter_compositions,
)
from backend.retrieval.poem.serving import ServingCandidate


def _candidate(name: str, author: str, text: str) -> ServingCandidate:
    return ServingCandidate(
        rank=1,
        work_id=name,
        author=author,
        text=text,
        title=name,
        dynasty="宋",
        source_record_id=name,
        chronology_status="same_dynasty",
        support_count=1,
    )


def _lookup(tmp_path: Path) -> WorkCompositionLookup:
    db_path = tmp_path / "work_compositions.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE work_compositions (
            parent_work_id TEXT, member_work_id TEXT, member_order INT,
            start_char INT, end_char INT, match_kind TEXT
        );
        CREATE INDEX work_composition_member ON work_compositions(member_work_id);
        CREATE INDEX work_composition_parent ON work_compositions(parent_work_id);
        INSERT INTO work_compositions VALUES ('group', 'one', 1, 0, 64, 'exact_concatenation');
        INSERT INTO work_compositions VALUES ('group', 'two', 2, 64, 128, 'exact_concatenation');
        """
    )
    connection.commit()
    connection.close()
    (tmp_path / "work_compositions_manifest.json").write_text(
        json.dumps({"corpus_sha256": "test-version", "relation_rows": 2}),
        encoding="utf8",
    )
    return WorkCompositionLookup(db_path, work_sha256="test-version")


def test_exact_self_work_filters_aggregate_even_when_member_was_already_removed(
    tmp_path: Path,
):
    lookup = _lookup(tmp_path)
    poem = "片片轻鸥落晚沙。"
    rows = [
        _candidate("group", "陆游", poem),
        _candidate("dufu", "杜甫", "片片轻鸥下急湍。"),
    ]
    assert lookup.excluded_parents(rows, {"two"}, current_text=poem) == {"group"}
    filtered = filter_compositions(
        rows, {"two"}, lookup, current_text=poem, final_top_k=8,
    )
    assert [c.work_id for c in filtered] == ["dufu"]


def test_self_group_hit_from_other_member_must_be_preserved(tmp_path: Path):
    lookup = _lookup(tmp_path)
    # 当前作品是 member two，但合集返回的是 member one 的另一个片段。
    rows = [
        _candidate("group", "陆游", "家住东吴近帝乡。"),
        _candidate("dufu", "杜甫", "片片轻鸥下急湍。"),
    ]
    assert lookup.excluded_parents(
        rows, {"two"}, current_text="片片轻鸥落晚沙。",
    ) == set()


def test_co_retrieved_member_filters_only_when_hit_overlaps(tmp_path: Path):
    lookup = _lookup(tmp_path)
    poem = "片片轻鸥落晚沙。"
    rows = [
        _candidate("group", "陆游", poem),
        _candidate("two", "陆游", poem),
        _candidate("dufu", "杜甫", "片片轻鸥下急湍。"),
        _candidate("more", "李白", "青天有月来几时。"),
    ]
    filtered = filter_compositions(
        rows, set(), lookup, current_text="", final_top_k=3,
    )
    assert [c.work_id for c in filtered] == ["two", "dufu", "more"]
    rows[1] = _candidate("two", "陆游", "懒向青门学种瓜。")
    assert lookup.excluded_parents(rows, set(), current_text="") == set()


def test_no_relation_no_guess_and_no_global_aggregate_ban(tmp_path: Path):
    lookup = _lookup(tmp_path)
    rows = [_candidate("group", "陆游", "片片轻鸥落晚沙。")]
    assert [
        c.work_id for c in filter_compositions(
            rows, set(), lookup, current_text="", final_top_k=8,
        )
    ] == ["group"]


def test_invalid_or_mismatched_relation_snapshot_fails_closed(tmp_path: Path):
    lookup = _lookup(tmp_path)
    with pytest.raises(ValueError, match="SHA-256"):
        WorkCompositionLookup(lookup.path, work_sha256="another-corpus")
    with pytest.raises(ValueError, match="manifest"):
        WorkCompositionLookup(
            lookup.path.with_name("missing.db"), work_sha256="test-version",
        )
    manifest = tmp_path / "work_compositions_manifest.json"
    manifest.write_text(
        json.dumps({"corpus_sha256": "test-version", "relation_rows": 3}),
        encoding="utf8",
    )
    with pytest.raises(ValueError, match="行数"):
        WorkCompositionLookup(lookup.path, work_sha256="test-version")
