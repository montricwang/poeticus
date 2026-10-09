"""使用合成数据测试本地公网作品迁移，不连接真实数据库。"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from uuid import UUID

import pytest

from scripts.corpus.public_corpus_transfer import (
    PUBLIC_COLUMNS, validate_public_rows, public_fingerprint, transfer,
)


def example(order: int) -> dict[str, object]:
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


class Result:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return deepcopy(self.rows)


class FakeCopy:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write_row(self, params):
        if self.conn.fail_after is not None and self.conn.writes >= self.conn.fail_after:
            raise RuntimeError("synthetic COPY interruption")
        row = dict(zip(PUBLIC_COLUMNS, params, strict=True))
        for key in ("body_segments", "prefaces"):
            wrapped = row[key]
            assert hasattr(wrapped, "obj")
            row[key] = wrapped.obj
        self.conn.rows.append(row)
        self.conn.writes += 1


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def copy(self, sql):
        assert sql.startswith("COPY poems (") and sql.endswith(") FROM STDIN")
        return FakeCopy(self.conn)


class FakeConn:
    def __init__(self, rows, fail_after=None):
        self.rows = deepcopy(rows)
        self.writes = 0
        self.fail_after = fail_after

    @contextmanager
    def transaction(self):
        backup = deepcopy(self.rows)
        try:
            yield
        except BaseException:
            self.rows = backup
            raise

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        if sql.startswith("SET LOCAL"):
            return Result()
        if sql.startswith("SELECT"):
            return Result(sorted(self.rows, key=lambda r: r["source_order"]))
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


def test_insert_into_empty_database():
    source = [example(1), example(2)]
    dest = FakeConn([])
    assert transfer(source, dest) == "inserted_into_empty"
    assert public_fingerprint(dest.rows) == public_fingerprint(source)
    assert len(dest.rows) == 2


def test_idempotent_repeat_does_not_write():
    source = [example(1), example(2)]
    dest = FakeConn(source)
    assert transfer(source, dest) == "already_identical"
    assert dest.writes == 0


def test_refuse_unknown_existing_records_without_mutating_them():
    source = [example(1)]
    cloud_rows = [example(2)]
    dest = FakeConn(cloud_rows)
    with pytest.raises(ValueError, match="非预期数据"):
        transfer(source, dest)
    assert dest.rows == cloud_rows
    assert dest.writes == 0


def test_copy_interrupt_rolls_back_partial_records():
    dest = FakeConn([], fail_after=1)
    with pytest.raises(RuntimeError, match="COPY interruption"):
        transfer([example(1), example(2)], dest)
    assert dest.rows == []
