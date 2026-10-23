"""Verify private Conversation/Message ownership against PostgreSQL transactions.

Tests use synthetic users within a transaction that is rolled back after each
test, so they never persist real users or need external Clerk credentials.
"""

import os
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from backend.api import auth as auth_api
from backend.api import chat as chat_api
from backend.api import conversations as conversations_api
from backend.auth.clerk import require_clerk_user
from backend.users import private_data

load_dotenv()

PAYLOAD = {
    "poem": "明月几时有",
    "question": "喜欢苏轼的豪放词",
    "context": {"id": "poem-001", "title": "水调歌头"},
    "turn_number": 1,
}


@pytest.fixture
def private_sql(monkeypatch):
    dsn = os.getenv("POETICUS_DATABASE_URL")
    if not dsn:
        pytest.skip("Local private PostgreSQL is not configured")
    conn = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=3)
    a, b = uuid4(), uuid4()
    try:
        for user_id, clerk_id in [(a, "user_integration_alice"), (b, "user_integration_bob")]:
            conn.execute(
                "INSERT INTO app_users (id, clerk_user_id) VALUES (%s, %s)",
                (user_id, clerk_id),
            )

        @contextmanager
        def test_connection():
            yield conn

        monkeypatch.setattr(private_data, "_db", test_connection)
        monkeypatch.setattr(
            chat_api, "get_or_create_user",
            lambda clerk_id: a if clerk_id == "user_integration_alice" else b,
        )
        monkeypatch.setattr(
            conversations_api, "get_or_create_user",
            lambda clerk_id: a if clerk_id == "user_integration_alice" else b,
        )
        monkeypatch.setattr(
            auth_api, "get_or_create_user",
            lambda clerk_id: a if clerk_id == "user_integration_alice" else b,
        )
        app = FastAPI()
        app.include_router(chat_api.router)
        app.include_router(conversations_api.router)
        app.include_router(auth_api.router)

        def fake_trusted_token(request: Request):
            return "user_integration_alice" if request.headers["Authorization"] == "Bearer A" else "user_integration_bob"

        app.dependency_overrides[require_clerk_user] = fake_trusted_token
        monkeypatch.setattr(chat_api, "require_clerk_user", fake_trusted_token)
        yield TestClient(app), a, b, conn
    finally:
        conn.rollback()
        conn.close()


def _chat(client, conversation_id, token="A"):
    return client.post(
        "/api/chat",
        headers={"Authorization": "Bearer " + token},
        json={**PAYLOAD, "conversation_id": str(conversation_id)},
    )


def test_stream_saves_turn_and_other_user_cannot_access(private_sql, monkeypatch):
    client, a, b, conn = private_sql
    monkeypatch.setattr(
        chat_api.graph,
        "stream",
        lambda *args, **kwargs: iter([("updates", {"agent": {"reply": "苏轼词既豪迈又细腻"}})]),
    )
    cid = uuid4()
    response = client.post(
        "/api/chat/stream",
        headers={"Authorization": "Bearer A"},
        json={**PAYLOAD, "conversation_id": str(cid)},
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    own = client.get("/api/conversations/" + str(cid), headers={"Authorization": "Bearer A"})
    assert own.status_code == 200
    assert [msg["role"] for msg in own.json()["messages"]] == ["user", "assistant"]
    assert own.json()["messages"][1]["content"] == "苏轼词既豪迈又细腻"
    assert client.get("/api/conversations/" + str(cid), headers={"Authorization": "Bearer B"}).status_code == 404
    assert client.delete("/api/conversations/" + str(cid), headers={"Authorization": "Bearer B"}).status_code == 404
    assert _chat(client, cid, "B").status_code == 404
    assert client.get("/api/conversations", headers={"Authorization": "Bearer B"}).json()["conversations"] == []
    assert conn.execute("SELECT count(*) FROM app_messages WHERE conversation_id=%s", (cid,)).fetchone()["count"] == 2
    assert client.delete("/api/conversations/" + str(cid), headers={"Authorization": "Bearer A"}).status_code == 204
    assert client.get("/api/conversations/" + str(cid), headers={"Authorization": "Bearer A"}).status_code == 404


def test_json_chat_does_not_enable_memory_without_opt_in(private_sql, monkeypatch):
    client, a, b, conn = private_sql
    seen = []
    monkeypatch.setattr(chat_api.graph, "invoke", lambda state: seen.append(state) or {"reply": "答复"})
    monkeypatch.setattr(chat_api, "safe_recall", lambda *args: pytest.fail("No consent to recall"))
    monkeypatch.setattr(chat_api, "safe_remember", lambda *args, **kwargs: pytest.fail("No consent to save"))
    cid = uuid4()
    assert _chat(client, cid).status_code == 200
    assert seen[0].get("user_memory") is None
    assert client.get("/api/conversations", headers={"Authorization": "Bearer A"}).status_code == 200


def test_opted_in_user_is_scoped_to_own_memory(private_sql, monkeypatch):
    client, a, b, conn = private_sql
    private_data.set_memory_opt_in(a, True)
    saved = []
    monkeypatch.setattr(chat_api, "safe_recall", lambda user, question: ["喜欢引用原文"] if user == str(a) else [])
    monkeypatch.setattr(chat_api, "safe_remember", lambda *args, **kwargs: saved.append((args, kwargs)))
    seen = []
    monkeypatch.setattr(chat_api.graph, "invoke", lambda state: seen.append(state) or {"reply": "答复"})
    first = _chat(client, uuid4(), "A")
    assert first.status_code == 200
    assert seen[-1].get("user_memory") == ["喜欢引用原文"]
    assert saved and saved[0][0][0] == str(a)
    assert saved[0][1]["source_message_id"]
    second = _chat(client, uuid4(), "B")
    assert second.status_code == 200
    assert seen[-1].get("user_memory") is None
    assert len(saved) == 1


def test_unsigned_client_id_does_not_create_private_records(private_sql, monkeypatch):
    client, a, b, conn = private_sql
    monkeypatch.setattr(chat_api.graph, "invoke", lambda state: {"reply": "公共回答"})
    cid = uuid4()
    response = client.post("/api/chat", json={
        **PAYLOAD, "conversation_id": str(cid), "user_id": str(a)
    }, headers={"X-User-ID": str(a)})
    assert response.status_code == 200
    assert conn.execute(
        "SELECT count(*) FROM app_conversations WHERE id=%s", (cid,)
    ).fetchone()["count"] == 0


def test_turn_change_requires_new_discussion(private_sql, monkeypatch):
    client, a, b, conn = private_sql
    monkeypatch.setattr(chat_api.graph, "invoke", lambda state: {"reply": "答复"})
    cid = uuid4()
    assert _chat(client, cid).status_code == 200
    assert _chat(client, cid).status_code == 200
    changed = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer A"},
        json={**PAYLOAD, "question": "改写的问题", "conversation_id": str(cid)},
    )
    assert changed.status_code == 409

def test_memory_consent_isolated_in_database(private_sql):
    client, alice, bob, conn = private_sql
    a = client.put(
        "/api/auth/memory-preference",
        headers={"Authorization": "Bearer A"},
        json={"enabled": True, "user_id": str(bob)},
    )
    assert a.status_code == 200
    assert a.json()["memory_opt_in"] is True
    assert private_data.get_memory_opt_in(alice) is True
    assert private_data.get_memory_opt_in(bob) is False
    invalid = client.put(
        "/api/auth/memory-preference",
        headers={"Authorization": "Bearer B"},
        json={"enabled": "not a bool"},
    )
    assert invalid.status_code == 422

def test_foreign_delete_does_not_even_scan_memory(private_sql, monkeypatch):
    client, alice, bob, conn = private_sql
    monkeypatch.setattr(chat_api.graph, "invoke", lambda state: {"reply": "答复"})
    cid = uuid4()
    assert _chat(client, cid, "A").status_code == 200
    from backend.memory import user_memory
    monkeypatch.setattr(
        user_memory, "remove_conversation_memories",
        lambda *args: pytest.fail("Memory scanned before ownership verification"),
    )
    assert client.delete(
        "/api/conversations/" + str(cid), headers={"Authorization": "Bearer B"},
    ).status_code == 404
