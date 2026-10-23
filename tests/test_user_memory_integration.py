"""Memory wiring tests: trusted identity, graph input, and SSE completion."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import chat as chat_api
from backend.memory import user_memory

PAYLOAD = {"poem": "明月几时有。", "question": "赏析这首词"}


def _api(*, trusted: bool, has_source: bool = True, consent: bool = True):
    app = FastAPI()
    app.include_router(chat_api.router)
    if trusted:
        @app.middleware("http")
        async def fake_authenticated_server(request, call_next):
            # Simulate future trusted auth + Conversation persistence middleware.
            request.state.authenticated_user_id = "user-001"
            request.state.user_memory_opt_in = consent
            if has_source:
                request.state.conversation_id = "conv-001"
                request.state.persisted_user_message_id = "msg-001"
            return await call_next(request)
    return TestClient(app)


def test_public_chat_never_accepts_client_declared_user_identity(monkeypatch):
    received = []
    monkeypatch.setattr(
        chat_api.graph,
        "invoke",
        lambda state: received.append(state) or {"reply": "正文"},
    )
    monkeypatch.setattr(
        chat_api,
        "safe_recall",
        lambda *a, **kw: pytest.fail("untrusted memory lookup"),
    )
    monkeypatch.setattr(
        chat_api,
        "safe_remember",
        lambda *a, **kw: pytest.fail("untrusted memory write"),
    )
    response = _api(trusted=False).post(
        "/api/chat",
        json={**PAYLOAD, "user_id": "stolen-user"},
        headers={"X-User-ID": "stolen-user"},
    )
    assert response.status_code == 200
    assert received[0].get("user_memory") is None


def test_trusted_json_chat_reads_and_writes_after_success(monkeypatch):
    writes = []
    received = []
    monkeypatch.setattr(
        chat_api,
        "safe_recall",
        lambda user, query: ["用户喜欢引用原文"] if user == "user-001" else [],
    )
    monkeypatch.setattr(
        chat_api, "safe_remember", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    monkeypatch.setattr(
        chat_api.graph,
        "invoke",
        lambda state: received.append(state) or {"reply": "赏析正文"},
    )
    response = _api(trusted=True).post("/api/chat", json=PAYLOAD)
    assert response.status_code == 200
    assert received[0]["user_memory"] == ["用户喜欢引用原文"]
    assert writes == [
        (
            ("user-001", "赏析这首词"),
            {"conversation_id": "conv-001", "source_message_id": "msg-001"},
        )
    ]


def test_no_unpersisted_message_write(monkeypatch):
    writes = []
    monkeypatch.setattr(chat_api, "safe_recall", lambda *_: [])
    monkeypatch.setattr(
        chat_api, "safe_remember", lambda *a, **kw: writes.append((a, kw))
    )
    monkeypatch.setattr(
        chat_api.graph, "invoke", lambda state: {"reply": "完成"}
    )
    response = _api(trusted=True, has_source=False).post("/api/chat", json=PAYLOAD)
    assert response.status_code == 200
    assert writes == []


def test_logged_in_user_without_memory_opt_in_has_no_memory(monkeypatch):
    monkeypatch.setattr(
        chat_api,
        "safe_recall",
        lambda *a, **kw: pytest.fail("unconsented lookup"),
    )
    monkeypatch.setattr(
        chat_api,
        "safe_remember",
        lambda *a, **kw: pytest.fail("unconsented write"),
    )
    monkeypatch.setattr(
        chat_api.graph, "invoke", lambda state: {"reply": "完成"}
    )
    response = _api(trusted=True, consent=False).post("/api/chat", json=PAYLOAD)
    assert response.status_code == 200


def test_failed_chat_does_not_write_memory(monkeypatch):
    writes = []
    monkeypatch.setattr(chat_api, "safe_recall", lambda *_: [])
    monkeypatch.setattr(
        chat_api, "safe_remember", lambda *a, **kw: writes.append((a, kw))
    )
    def failure(state):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(chat_api.graph, "invoke", failure)
    response = _api(trusted=True).post("/api/chat", json=PAYLOAD)
    assert response.status_code == 502
    assert writes == []


def test_trusted_stream_writes_only_after_done(monkeypatch):
    writes, inputs = [], []
    monkeypatch.setattr(
        chat_api, "safe_recall", lambda user, query: ["偏好清楚引用来源"]
    )
    def remember(*a, **kw):
        writes.append((a, kw))
    monkeypatch.setattr(chat_api, "safe_remember", remember)

    def fake_stream(state, stream_mode):
        inputs.append(state)
        yield ("updates", {"agent": {"reply": "完成", "tool_calls": []}})

    monkeypatch.setattr(chat_api.graph, "stream", fake_stream)
    result = _api(trusted=True).post("/api/chat/stream", json=PAYLOAD)
    assert result.status_code == 200
    assert "event: done" in result.text
    assert inputs[0]["user_memory"] == ["偏好清楚引用来源"]
    assert len(writes) == 1


def test_stream_error_never_writes(monkeypatch):
    writes = []
    monkeypatch.setattr(chat_api, "safe_recall", lambda *_: [])
    monkeypatch.setattr(
        chat_api, "safe_remember", lambda *a, **kw: writes.append((a, kw))
    )
    def fail_stream(state, stream_mode):
        raise RuntimeError("fail")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_api.graph, "stream", fail_stream)
    result = _api(trusted=True).post("/api/chat/stream", json=PAYLOAD)
    assert "event: error" in result.text
    assert writes == []


def test_memory_off_does_not_load_sdk(monkeypatch):
    monkeypatch.setattr(user_memory.config, "USER_MEMORY_ENABLED", False)
    monkeypatch.setattr(
        user_memory,
        "_memory",
        lambda: pytest.fail("disabled memory loaded SDK"),
    )
    assert user_memory.safe_recall("user-001", "偏好") == []
    user_memory.safe_remember(
        "user-001", "内容", conversation_id="conv-001", source_message_id="msg-001"
    )


def test_agent_reads_memory_as_context(monkeypatch):
    from backend.ai import graph as agent_module
    from types import SimpleNamespace

    observed = []

    def fake_create(**kwargs):
        observed.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="苏轼", tool_calls=None
                    )
                )
            ]
        )

    monkeypatch.setattr(
        agent_module,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )
    result = agent_module.agent_decide({
        "poem": "明月几时有。",
        "question": "我最近研究谁？",
        "user_memory": ["读者最近研究苏轼"],
        "tool_count": agent_module.AGENT_MAX_TOOL_CALLS,
    })
    assert result["reply"] == "苏轼"
    assert any("读者最近研究苏轼" in str(m.get("content")) for m in observed)
    assert all("user_memory" not in str(m) for m in observed)



def test_confirmed_memory_follows_old_history_before_current_question(monkeypatch):
    """Old chat must not be the last personal-preference authority sent to the LLM."""
    from backend.ai import graph as agent_module
    from types import SimpleNamespace

    observed = []

    def fake_create(**kwargs):
        observed.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="李清照", tool_calls=None)
                )
            ]
        )

    monkeypatch.setattr(
        agent_module,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    agent_module.agent_decide({
        "poem": "明月几时有。",
        "question": "我最喜欢哪位词人？",
        "user_memory": ["【本人已更正的现行记忆】我最喜欢李清照"],
        "history": [
            {"role": "user", "content": "我最喜欢姜夔"},
            {"role": "assistant", "content": "记住了，是姜夔"},
        ],
        "tool_count": agent_module.AGENT_MAX_TOOL_CALLS,
    })

    old_index = next(i for i, m in enumerate(observed) if m["content"] == "我最喜欢姜夔")
    correction_index = next(
        i for i, m in enumerate(observed)
        if m["role"] == "system" and "读者已在账号的记忆管理界面明确更正" in str(m["content"])
    )
    assert old_index < correction_index < len(observed) - 1
    assert "李清照" in str(observed[correction_index]["content"])


def test_inferred_memory_does_not_forge_explicit_user_correction(monkeypatch):
    from backend.ai import graph as agent_module
    from types import SimpleNamespace

    observed = []

    def fake_create(**kwargs):
        observed.extend(kwargs["messages"])
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="不确定", tool_calls=None)
                )
            ]
        )

    monkeypatch.setattr(
        agent_module,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    agent_module.agent_decide({
        "poem": "明月几时有。",
        "question": "我最喜欢哪位词人？",
        "user_memory": ["【从旧对话提取、可能过时】我喜欢姜夔"],
        "tool_count": agent_module.AGENT_MAX_TOOL_CALLS,
    })
    assert not any(
        m["role"] == "system" and "读者已在账号的记忆管理界面明确更正" in str(m["content"])
        for m in observed
    )
