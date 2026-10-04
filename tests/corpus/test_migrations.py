"""Versioned migration runner uses existing versions and never reapplies DDL."""
from contextlib import nullcontext
from types import SimpleNamespace

from scripts.corpus import db_import


class FakeMigrationConnection:
    def __init__(self, versions):
        self.versions = set(versions)
        self.executed = []

    def transaction(self):
        return nullcontext()

    def execute(self, statement, args=()):
        self.executed.append((statement, args))
        if statement == "SELECT version FROM schema_migrations":
            return SimpleNamespace(fetchall=lambda: [(v,) for v in self.versions])
        if statement.startswith("INSERT INTO schema_migrations"):
            self.versions.add(args[0])
        return SimpleNamespace(fetchall=lambda: [])


ALL = {"0001_corpus", "0002_cipai", "0003_yusheng_title", "0004_ai_daily_quotas"}


def _ddl(conn):
    return [sql for sql, _ in conn.executed if "ALTER TABLE poems" in sql]


def test_existing_0001_database_applies_two_renames_and_ai_quota_once():
    conn = FakeMigrationConnection(["0001_corpus"])
    db_import.migrate(conn)
    assert conn.versions == ALL
    applied_sql = _ddl(conn)
    assert len(applied_sql) == 2
    assert "RENAME COLUMN tune TO cipai" in applied_sql[0]
    assert "ALTER INDEX idx_poems_tune_order" in applied_sql[0]
    assert "RENAME COLUMN yusheng TO yusheng_title" in applied_sql[1]
    before = len(conn.executed)
    db_import.migrate(conn)
    assert not any("ALTER TABLE poems" in sql for sql, _ in conn.executed[before:])


def test_existing_0002_database_applies_yusheng_and_ai_quota():
    conn = FakeMigrationConnection(["0001_corpus", "0002_cipai"])
    db_import.migrate(conn)
    assert conn.versions == ALL
    assert len(_ddl(conn)) == 1
    assert "RENAME COLUMN yusheng TO yusheng_title" in _ddl(conn)[0]


def test_fresh_database_applies_all_migrations_in_sequence():
    conn = FakeMigrationConnection([])
    db_import.migrate(conn)
    assert conn.versions == ALL
    ddl = [sql for sql, _ in conn.executed if "CREATE TABLE poems" in sql]
    assert len(ddl) == 1
    assert [sql for sql, _ in conn.executed if "ALTER TABLE poems" in sql] == [
        next(sql for sql, _ in conn.executed if "RENAME COLUMN tune TO cipai" in sql),
        next(sql for sql, _ in conn.executed if "RENAME COLUMN yusheng TO yusheng_title" in sql),
    ]



def test_existing_0003_database_adds_only_quota_table():
    conn = FakeMigrationConnection(["0001_corpus", "0002_cipai", "0003_yusheng_title"])
    db_import.migrate(conn)
    assert conn.versions == ALL
    assert len(_ddl(conn)) == 0
    assert any("CREATE TABLE ai_daily_quotas" in sql for sql, _ in conn.executed)
