"""Migration runner tracks versions; syntax changes are not silent rewrites."""
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


def test_upgrade_0001_only_database_to_cipai():
    conn = FakeMigrationConnection(["0001_corpus"])
    db_import.migrate(conn)
    assert conn.versions == {"0001_corpus", "0002_cipai"}
    applied_sql = [sql for sql, _ in conn.executed if "ALTER TABLE poems" in sql]
    assert len(applied_sql) == 1
    assert "RENAME COLUMN tune TO cipai" in applied_sql[0]
    assert "ALTER INDEX idx_poems_tune_order" in applied_sql[0]
    before = len(conn.executed)
    db_import.migrate(conn)
    assert not any("ALTER TABLE poems" in sql for sql, _ in conn.executed[before:])


def test_fresh_database_applies_both_migrations():
    conn = FakeMigrationConnection([])
    db_import.migrate(conn)
    assert conn.versions == {"0001_corpus", "0002_cipai"}
    ddl = [sql for sql, _ in conn.executed if "CREATE TABLE poems" in sql]
    assert len(ddl) == 1
