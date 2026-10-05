"""公开服务接口必须保持轻量，并且不能泄露运行时秘密。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    import backend.app as api

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


def test_capabilities_exposes_browser_contract_without_secrets(client):
    from backend.config import (
        CHAT_MAX_HISTORY_TURNS,
        CHAT_MAX_QUESTION_CHARS,
        CHAT_MAX_SELECTION_CHARS,
    )

    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "chat": {
            "maxHistoryTurns": CHAT_MAX_HISTORY_TURNS,
            "maxQuestionChars": CHAT_MAX_QUESTION_CHARS,
            "maxSelectionChars": CHAT_MAX_SELECTION_CHARS,
        }
    }
    assert "test-only-placeholder" not in response.text


def test_public_chat_path_works(monkeypatch, client):
    import backend.app as api

    calls = []

    def fake_invoke(state):
        calls.append(state["question"])
        return {"reply": "合成回答"}

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(invoke=fake_invoke))
    payload = {"poem": "春风吹。", "question": "解释春风"}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert response.json() == {"answer": "合成回答"}
    assert calls == ["解释春风"]


def test_canonical_public_analyze_path(monkeypatch, client):
    from backend.ai.model import PoemAnalysis

    monkeypatch.setattr("backend.api.analysis.analyze_poem",
        lambda poem, context: PoemAnalysis(
            translation="合成译文", glosses=[], commentary="合成赏析"
        ),
    )
    response = client.post("/api/analyze", json={"poem": "春风吹。"})
    assert response.status_code == 200
    assert response.json()["translation"] == "合成译文"


def test_canonical_public_sse_path(monkeypatch, client):
    import backend.app as api

    def fake_stream(state, stream_mode):
        yield "custom", {"type": "token", "text": "合成"}
        yield "updates", {"agent": {"reply": "合成", "tool_calls": []}}

    monkeypatch.setattr("backend.api.chat.graph", SimpleNamespace(stream=fake_stream))
    response = client.post(
        "/api/chat/stream", json={"poem": "春风吹。", "question": "解释"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: token\ndata: {"text": "合成"}' in response.text
    assert "event: done" in response.text
