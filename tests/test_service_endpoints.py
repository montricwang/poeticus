"""Public service endpoints must remain cheap and disclose no runtime secrets."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import api

    return TestClient(api.app)


def test_health_does_not_need_database_or_ai(monkeypatch, client):
    import backend.corpus.connection as connection

    def must_not_connect(*args, **kwargs):
        raise AssertionError("health must not open PostgreSQL")

    monkeypatch.setattr(connection.psycopg, "connect", must_not_connect)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_exposes_only_intended_public_metadata(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    assert response.json() == {
        "name": "Poeticus",
        "version": client.app.version,
        "repository": "https://github.com/montricwang/poeticus",
    }
    assert "test-only-placeholder" not in response.text
    assert client.get("/openapi.json").json()["info"]["version"] == client.app.version
