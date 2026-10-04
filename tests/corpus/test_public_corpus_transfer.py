"""Synthetic tests of the local-only public corpus transfer; no actual DB."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from uuid import UUID

import pytest

from scripts.corpus.public_corpus_transfer import (
    DEMO_IDS, PUBLIC_COLUMNS, validate_public_rows, public_fingerprint, transfer,
)


def example(order: int) -> dict:
    return {
        "id": UUID(f"10000000-0000-4000-8000-{order:012d}"),
        "source_record_id": f"example-{order}",
        "source_order": order,
        "collection": "合成作品集",
        "author": "测试作者",
        "cipai": "模拟词牌",
        "title": f"题目{order}",
        "yusheng_title": None,
        "body_segments": ["清风过竹。", "明月照窗。"],
        "prefaces": [],
        "review_status": "imported_unreviewed",
        "text_version": 1,
    }


def demo(order: int) -> dict:
    row = example(order)
    row.update({
        "id": next(k for k, v in DEMO_IDS.items() if v == f"demo-synthetic-{order}"),
        "source_record_id": f"demo-synthetic-{order}",
        "collection": "Poeticus 合成测试作品",
        "review_status": "demo_synthetic",
    })
    return row


class Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return deepcopy(self.rows)


class FakeConn:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.writes = 0

    @contextmanager
    def transaction(self):
        backup = deepcopy(self.rows)
        try:
            yield
        except BaseException:
            self.rows = backup
            raise

    def execute(self, sql, params=None):
        if sql.startswith("SELECT"):
            return Result(sorted(self.rows, key=lambda r: r["source_order"]))
        if sql.startswith("DELETE"):
            deleted = set(params[0])
            self.rows = [r for r in self.rows if r["id"] not in deleted]
            self.writes += 1
            return Result()
        if sql.startswith("INSERT"):
            values = dict(zip(PUBLIC_COLUMNS, params, strict=True))
            # Psycopg adapters are not JSON data; fake server decodes JSONB.
            for key in ("body_segments", "prefaces"):
                values[key] = values[key].obj
            self.rows.append(values)
            self.writes += 1
            return Result()
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_whitelist_has_no_private_source_or_editorial_fields():
    for name in (
        "annotations", "commentary", "inline_notes", "lacunae",
        "original_segments", "original_inline_notes", "source_locator",
        "source_sha256", "source_title",
    ):
        assert name not in PUBLIC_COLUMNS


def test_validate_full_count_and_stable_fingerprint():
    rows = [example(1), example(2)]
    summary = validate_public_rows(rows, 2)
    assert summary["rows"] == 2
    assert summary["prefaces"] == 0
    assert summary["review_states"] == {"imported_unreviewed": 2}
    assert summary["sha256"] == public_fingerprint(rows)
    with pytest.raises(ValueError, match="预期"):
        validate_public_rows(rows, 3491)


def test_check_flags_suspicious_preface_without_printing_text():
    rows = [example(1)]
    rows[0]["prefaces"] = ["出版社编者按：这是合成的例子"]
    report = validate_public_rows(rows, 1)
    assert report["suspect_editorial_count"] == 1
    assert report["suspect_source_orders"] == [1]
    assert "出版社" not in str(report)


def test_check_rejects_duplicate_or_empty_poem():
    rows = [example(1), example(1)]
    with pytest.raises(ValueError, match="重复"):
        validate_public_rows(rows, 2)
    rows = [example(1)]
    rows[0]["body_segments"] = ["   "]
    with pytest.raises(ValueError, match="正文"):
        validate_public_rows(rows, 1)


def test_replace_only_matching_demo_data_atomically():
    source = [example(1), example(2)]
    dest = FakeConn([demo(1), demo(2), demo(3)])
    assert transfer(source, dest) == "replaced_known_demo"
    assert public_fingerprint(dest.rows) == public_fingerprint(source)
    assert len(dest.rows) == 2
    assert dest.writes == 3


def test_idempotent_repeat_does_not_write():
    source = [example(1), example(2)]
    dest = FakeConn(source)
    assert transfer(source, dest) == "already_identical"
    assert dest.writes == 0


def test_refuse_non_demo_records_without_mutating_them():
    source = [example(1)]
    cloud_rows = [demo(1), example(2)]
    dest = FakeConn(cloud_rows)
    with pytest.raises(ValueError, match="非预期数据"):
        transfer(source, dest)
    assert dest.rows == cloud_rows
    assert dest.writes == 0
