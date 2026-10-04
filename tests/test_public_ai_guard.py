"""Public Web AI admission tests; never connect to DeepSeek or real Postgres."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import public_ai_guard


def make_app(monkeypatch, *, enabled=True, minute=5, daily_ok=True):
    monkeypatch.setenv("POETICUS_AI_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("POETICUS_AI_PER_IP_PER_MINUTE", str(minute))
    monkeypatch.setenv("POETICUS_AI_MAX_CONCURRENT", "2")
    monkeypatch.setenv("POETICUS_AI_DAILY_REQUESTS", "3")
    monkeypatch.setenv("POETICUS_DATABASE_URL", "postgresql://fake/not-connected")

    reservations = []
    def fake_reserve(dsn, limit):
        reservations.append((dsn, limit))
        return daily_ok

    monkeypatch.setattr(public_ai_guard, "_reserve_daily_slot", fake_reserve)
    app = FastAPI()

    @app.post("/api/chat/stream")
    def paid():
        return {"text": "synthetic, no model"}

    @app.post("/analyze")
    def analyze():
        return {"translation": "synthetic"}

    @app.get("/api/poems")
    def poems():
        return {"total": 3491}

    app.add_middleware(public_ai_guard.PublicAIGuard)
    return TestClient(app), reservations


def test_default_disabled_blocks_models_but_not_poems(monkeypatch):
    cli, spent = make_app(monkeypatch, enabled=False)
    assert cli.get("/api/poems").json() == {"total": 3491}
    response = cli.post("/api/chat/stream", json={"question": "hi"})
    assert response.status_code == 503
    assert spent == []


def test_valid_requests_reserve_budget_on_all_paid_routes(monkeypatch):
    cli, spent = make_app(monkeypatch)
    assert cli.post("/api/chat/stream", json={"question": "test"}).status_code == 200
    assert cli.post("/analyze", json={"poem": "test"}).status_code == 200
    assert len(spent) == 2
    assert all(x[1] == 3 for x in spent)


def test_per_peer_rate_limit_is_server_side(monkeypatch):
    cli, spent = make_app(monkeypatch, minute=1)
    assert cli.post("/api/chat/stream", json={"question": "x"}).status_code == 200
    second = cli.post("/api/chat/stream", json={"question": "x"})
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
    assert len(spent) == 1


def test_daily_budget_exhaustion_blocks_paid_routes(monkeypatch):
    cli, spent = make_app(monkeypatch, daily_ok=False)
    response = cli.post("/api/chat/stream", json={"question": "x"})
    assert response.status_code == 429
    assert "今日" in response.json()["detail"]
    assert len(spent) == 1
    assert cli.get("/api/poems").status_code == 200


def test_large_chunked_or_regular_body_blocked_before_budget(monkeypatch):
    cli, spent = make_app(monkeypatch)
    response = cli.post("/api/chat/stream", content=b"x" * (public_ai_guard.MAX_REQUEST_BYTES + 1))
    assert response.status_code == 413
    assert spent == []


def test_concurrency_cap_and_release(monkeypatch):
    cli, spent = make_app(monkeypatch)
    guard = public_ai_guard.PublicAIGuard(lambda *_args: None)
    assert guard._acquire("first")[0]
    assert guard._acquire("second")[0]
    assert guard._acquire("third") == (False, 5)
    guard._release()
    assert guard._acquire("third")[0]
    guard._release()
    guard._release()
    assert guard.active == 0



def test_railway_real_ip_only_when_explicitly_trusted(monkeypatch):
    monkeypatch.setenv("POETICUS_AI_ENABLED", "true")
    monkeypatch.delenv("POETICUS_TRUST_RAILWAY_REAL_IP", raising=False)
    guard = public_ai_guard.PublicAIGuard(lambda *_args: None)
    scope = {
        "client": ("10.0.0.2", 43000),
        "headers": [(b"x-real-ip", b"203.0.113.8"), (b"x-forwarded-for", b"1.1.1.1")],
    }
    assert guard._client_identity(scope) == "10.0.0.2"
    monkeypatch.setenv("POETICUS_TRUST_RAILWAY_REAL_IP", "true")
    guard = public_ai_guard.PublicAIGuard(lambda *_args: None)
    assert guard._client_identity(scope) == "203.0.113.8"
    scope["headers"] = [(b"x-real-ip", b"invalid,1.2.3.4")]
    assert guard._client_identity(scope) == "10.0.0.2"
