from backend.api import analysis as analysis_routes
from backend.api import chat as chat_routes
"""Public service endpoints must remain cheap and disclose no runtime secrets."""

from types import SimpleNamespace

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


def test_canonical_public_chat_path_and_legacy_path_both_work(monkeypatch, client):
    import api

    calls = []

    def fake_invoke(state):
        calls.append(state["question"])
        return {"reply": "合成回答"}

    monkeypatch.setattr(chat_routes, "graph", SimpleNamespace(invoke=fake_invoke))
    payload = {"poem": "春风吹。", "question": "解释春风"}
    for path in ("/chat", "/api/chat"):
        response = client.post(path, json=payload)
        assert response.status_code == 200
        assert response.json() == {"answer": "合成回答"}
    assert calls == ["解释春风", "解释春风"]


def test_canonical_public_analyze_path(monkeypatch, client):
    import api

    monkeypatch.setattr(
        analysis_routes,
        "analyze_poem",
        lambda poem, context: api.PoemAnalysis(
            translation="合成译文", glosses=[], commentary="合成赏析"
        ),
    )
    response = client.post("/api/analyze", json={"poem": "春风吹。"})
    assert response.status_code == 200
    assert response.json()["translation"] == "合成译文"


def test_canonical_public_sse_path(monkeypatch, client):
    import api

    def fake_stream(state, stream_mode):
        yield "custom", {"type": "token", "text": "合成"}
        yield "updates", {"agent": {"reply": "合成", "tool_calls": []}}

    monkeypatch.setattr(chat_routes, "graph", SimpleNamespace(stream=fake_stream))
    response = client.post(
        "/api/chat/stream", json={"poem": "春风吹。", "question": "解释"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: token\ndata: {"text": "合成"}' in response.text
    assert "event: done" in response.text
