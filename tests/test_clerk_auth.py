"""Clerk is the identity authority; no user ID from the client is trusted."""

from types import SimpleNamespace
from uuid import UUID

import clerk_backend_api
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.api import auth as auth_api
from backend.api.auth import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _configured(monkeypatch):
    monkeypatch.setattr(config, "CLERK_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(config, "CLERK_JWT_KEY", None)
    monkeypatch.setattr(
        config,
        "CLERK_AUTHORIZED_PARTIES",
        ("http://localhost:5173", "http://127.0.0.1:5173"),
    )
    monkeypatch.setattr(
        auth_api,
        "get_or_create_user",
        lambda clerk_id: UUID("11111111-2222-4333-8444-555555555555"),
    )
    monkeypatch.setattr(auth_api, "get_memory_opt_in", lambda _user_id: False)


def test_auth_endpoint_requires_configuration(monkeypatch):
    monkeypatch.setattr(config, "CLERK_SECRET_KEY", "")
    monkeypatch.setattr(config, "CLERK_AUTHORIZED_PARTIES", ())
    response = _client().get("/api/auth/me")
    assert response.status_code == 503
    assert response.json() == {"detail": "身份验证尚未配置"}


def test_auth_endpoint_requires_authorized_frontend_origins(monkeypatch):
    monkeypatch.setattr(config, "CLERK_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(config, "CLERK_AUTHORIZED_PARTIES", ())
    assert _client().get("/api/auth/me").status_code == 503


def test_auth_endpoint_returns_only_verified_clerk_subject(monkeypatch):
    _configured(monkeypatch)
    seen = []

    def fake_authenticate(request, options):
        seen.append((request, options))
        verified = request.headers.get("Authorization") == "Bearer valid-session"
        return SimpleNamespace(
            is_signed_in=verified,
            payload={"sub": "user_signed_proof"} if verified else None,
        )

    monkeypatch.setattr(clerk_backend_api, "authenticate_request", fake_authenticate)

    client = _client()
    assert client.get("/api/auth/me").status_code == 401
    denied = client.get(
        "/api/auth/me",
        headers={"X-User-ID": "user_signed_proof", "Authorization": "Bearer bogus"},
    )
    assert denied.status_code == 401

    approved = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer valid-session"}
    )
    assert approved.status_code == 200
    assert approved.json() == {"clerk_user_id": "user_signed_proof"}

    account = client.post(
        "/api/auth/session", headers={"Authorization": "Bearer valid-session"}
    )
    assert account.status_code == 200
    assert account.json() == {
        "clerk_user_id": "user_signed_proof",
        "user_id": "11111111-2222-4333-8444-555555555555",
        "memory_opt_in": False,
        "memory_available": False,
    }
    assert account.headers["Cache-Control"] == "no-store"

    _, options = seen[-1]
    assert options.accepts_token == ["session_token"]
    assert options.authorized_parties == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_auth_rejects_subject_missing_or_malformed(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(
        clerk_backend_api,
        "authenticate_request",
        lambda *args, **kwargs: SimpleNamespace(
            is_signed_in=True, payload={"sub": "untrusted-client-value"}
        ),
    )
    response = _client().get("/api/auth/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 401


def test_auth_fails_closed_on_sdk_error(monkeypatch):
    _configured(monkeypatch)

    def failed_verification(*args, **kwargs):
        raise RuntimeError("simulated JWT validation failure")

    monkeypatch.setattr(clerk_backend_api, "authenticate_request", failed_verification)
    response = _client().get(
        "/api/auth/me", headers={"Authorization": "Bearer forged-token"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "登录凭证无效"}


def test_unverified_token_never_registers_user(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(
        auth_api,
        "get_or_create_user",
        lambda *args: (_ for _ in ()).throw(AssertionError("Unverified user was stored")),
    )
    monkeypatch.setattr(
        clerk_backend_api,
        "authenticate_request",
        lambda *args, **kwargs: SimpleNamespace(is_signed_in=False, payload=None),
    )
    assert _client().post("/api/auth/session").status_code == 401


def test_verified_login_returns_service_error_if_db_unavailable(monkeypatch):
    from fastapi import HTTPException

    _configured(monkeypatch)
    monkeypatch.setattr(
        clerk_backend_api,
        "authenticate_request",
        lambda *args, **kwargs: SimpleNamespace(
            is_signed_in=True, payload={"sub": "user_signed_proof"}
        ),
    )
    def offline_db(*args):
        raise HTTPException(status_code=503, detail="用户数据库暂时不可用")

    monkeypatch.setattr(auth_api, "get_or_create_user", offline_db)
    response = _client().post("/api/auth/session")
    assert response.status_code == 503
    assert "用户数据库" in response.json()["detail"]



def test_me_does_not_create_database_user(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(
        clerk_backend_api,
        "authenticate_request",
        lambda *args, **kwargs: SimpleNamespace(
            is_signed_in=True, payload={"sub": "user_signed_proof"}
        ),
    )
    monkeypatch.setattr(
        auth_api,
        "get_or_create_user",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("GET /api/auth/me must not write account records")
        ),
    )
    response = _client().get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"clerk_user_id": "user_signed_proof"}
