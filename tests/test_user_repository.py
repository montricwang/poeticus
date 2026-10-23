"""User mapping is scoped to verified external IDs and preserves one local UUID."""

from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from fastapi import HTTPException

from backend.users import repository


class MemoryConnection:
    def __init__(self):
        self.users = {}
        self.commands = []

    def execute(self, sql, params):
        self.commands.append((sql, params))
        if "INSERT INTO app_users" in sql:
            candidate, external = params
            if external in self.users:
                return SimpleNamespace(fetchone=lambda: None)
            self.users[external] = candidate
            return SimpleNamespace(fetchone=lambda: (candidate,))
        assert "SELECT id FROM app_users" in sql
        return SimpleNamespace(fetchone=lambda: (self.users[params[0]],))


def test_registration_stable_and_two_users_isolated():
    conn = MemoryConnection()
    first = repository._get_or_create_user(conn, "user_alice")
    again = repository._get_or_create_user(conn, "user_alice")
    second = repository._get_or_create_user(conn, "user_bob")
    assert isinstance(first, UUID)
    assert again == first
    assert second != first
    assert len(conn.users) == 2
    assert all("%s" in sql for sql, _ in conn.commands)


def test_invalid_external_user_rejected_without_connecting(monkeypatch):
    monkeypatch.setattr(
        repository.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("unexpected DB connection"),
    )
    with pytest.raises(ValueError):
        repository.get_or_create_user("client_supplied_id")


def test_database_missing_returns_service_unavailable(monkeypatch):
    monkeypatch.delenv("POETICUS_DATABASE_URL", raising=False)
    with pytest.raises(HTTPException) as err:
        repository.get_or_create_user("user_alice")
    assert err.value.status_code == 503


def test_connection_failures_hide_database_details(monkeypatch):
    monkeypatch.setenv("POETICUS_DATABASE_URL", "postgresql://fake:secret@invalid/db")

    def fail(*args, **kwargs):
        raise psycopg.OperationalError("secret connection failed")

    monkeypatch.setattr(repository.psycopg, "connect", fail)
    with pytest.raises(HTTPException) as err:
        repository.get_or_create_user("user_alice")
    assert err.value.status_code == 503
    assert "secret" not in err.value.detail
