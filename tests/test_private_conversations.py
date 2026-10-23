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


def test_memory_cutoff_blocks_queued_old_messages(private_sql, monkeypatch):
    """Database consent + source record + cutoff are checked at extraction time."""
    from backend.users.private_data import source_allows_memory, invalidate_pending_memory

    client, alice, bob, conn = private_sql
    cid = uuid4()
    first = private_data.begin_turn(alice, cid, "poem-001", 1, "我喜欢苏轼")
    assert not source_allows_memory(alice, cid, first, "我喜欢苏轼")

    private_data.set_memory_opt_in(alice, True)
    # Consent given after the message must not retroactively publish that message.
    assert not source_allows_memory(alice, cid, first, "我喜欢苏轼")

    second = private_data.begin_turn(alice, cid, "poem-001", 2, "我喜欢李清照")
    assert source_allows_memory(alice, cid, second, "我喜欢李清照")
    assert not source_allows_memory(bob, cid, second, "我喜欢李清照")
    assert not source_allows_memory(alice, cid, second, "不一样的原文")

    invalidate_pending_memory(alice)  # An explicit user correction or deletion.
    assert not source_allows_memory(alice, cid, second, "我喜欢李清照")

    third = private_data.begin_turn(alice, cid, "poem-001", 3, "现在喜欢王安石")
    assert source_allows_memory(alice, cid, third, "现在喜欢王安石")
    private_data.set_memory_opt_in(alice, False)
    assert not source_allows_memory(alice, cid, third, "现在喜欢王安石")


def test_memory_correction_and_single_delete_are_user_scoped(private_sql, monkeypatch):
    from backend.memory import user_memory

    class FakeMemory:
        def __init__(self, owner):
            self.data = {
                "mine": {
                    "id": "mine", "user_id": str(owner),
                    "memory": "喜欢苏轼",
                    "metadata": {
                        "source": "conversation",
                        "conversation_id": "some-old-conversation",
                    },
                },
            }

        def get(self, key):
            return dict(self.data[key]) if key in self.data else None

        def update(self, key, *, text, metadata):
            self.data[key]["memory"] = text
            self.data[key]["metadata"].update(metadata)

        def delete(self, key):
            del self.data[key]

        def get_all(self, *, filters, top_k):
            return {
                "results": [
                    dict(item) for item in self.data.values()
                    if item["user_id"] == filters["user_id"]
                ]
            }

    client, alice, bob, conn = private_sql
    fake = FakeMemory(alice)
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    monkeypatch.setattr(user_memory, "_has_memory_storage", lambda: True)

    foreign = client.patch(
        "/api/memories/mine", headers={"Authorization": "Bearer B"},
        json={"text": "恶意修改"},
    )
    assert foreign.status_code == 404
    assert conn.execute(
        "SELECT memory_reset_at FROM app_users WHERE id=%s", (bob,)
    ).fetchone()["memory_reset_at"] is None
    assert fake.data["mine"]["memory"] == "喜欢苏轼"

    corrected = client.patch(
        "/api/memories/mine", headers={"Authorization": "Bearer A"},
        json={"text": "现在更喜欢李清照"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["memory"] == "现在更喜欢李清照"
    assert fake.data["mine"]["metadata"]["source"] == "user_correction"
    assert fake.data["mine"]["metadata"]["conversation_id"] is None

    assert client.get("/api/memories", headers={"Authorization": "Bearer B"}).json()["memories"] == []
    assert client.delete("/api/memories/mine", headers={"Authorization": "Bearer B"}).status_code == 404
    assert client.delete("/api/memories/mine", headers={"Authorization": "Bearer A"}).status_code == 204
    assert fake.data == {}


def test_clear_memories_revokes_consent_and_prevents_future_old_writes(private_sql, monkeypatch):
    from backend.memory import user_memory

    client, alice, bob, conn = private_sql
    private_data.set_memory_opt_in(alice, True)
    cid = uuid4()
    mid = private_data.begin_turn(alice, cid, "poem-001", 1, "我喜欢苏轼")
    assert private_data.source_allows_memory(alice, cid, mid, "我喜欢苏轼")
    monkeypatch.setattr(user_memory, "_has_memory_storage", lambda: False)

    response = client.delete("/api/memories", headers={"Authorization": "Bearer A"})
    assert response.status_code == 200
    assert response.json() == {"deleted": 0, "memory_opt_in": False}
    assert private_data.get_memory_opt_in(alice) is False
    assert not private_data.source_allows_memory(alice, cid, mid, "我喜欢苏轼")
