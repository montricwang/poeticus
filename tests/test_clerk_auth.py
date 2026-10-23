"""Clerk is the identity authority; no user ID from the client is trusted."""

from types import SimpleNamespace

import clerk_backend_api
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
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
    assert approved.headers["Cache-Control"] == "no-store"

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
