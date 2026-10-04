"""Temporary staging protection tests; no actual DB or model required."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.preview_guard import PreviewGuard


def client() -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return {"message": "preview"}

    @app.get("/api/poems")
    def poems():
        return {"items": [{"title": "合成测试作品"}]}

    @app.post("/api/chat/stream")
    def costly_chat():
        raise AssertionError("read-only guard must block paid model calls")

    app.add_middleware(PreviewGuard, username="preview", password="test-secret")
    return TestClient(app)


def test_health_can_be_called_without_preview_password():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthorized_reader_gets_browser_login_challenge():
    http = client()
    for path in ("/", "/api/poems", "/docs", "/api/info"):
        response = http.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Basic realm="Poeticus Preview"'
        assert "test-secret" not in response.text


def test_preview_password_protects_all_read_routes():
    http = client()
    response = http.get("/api/poems", auth=("preview", "test-secret"))
    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "合成测试作品"
    assert http.get("/", auth=("preview", "test-secret")).status_code == 200


def test_wrong_or_malformed_credentials_rejected():
    http = client()
    assert http.get("/", auth=("preview", "bad-password")).status_code == 401
    assert http.get("/", auth=("someone", "test-secret")).status_code == 401
    assert http.get("/", headers={"Authorization": "Basic not-base64%%"}).status_code == 401


def test_ai_post_disabled_even_with_valid_preview_credentials():
    response = client().post(
        "/api/chat/stream",
        auth=("preview", "test-secret"),
        json={"question": "付费 AI 测试"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "当前为只读测试预览，AI 问答尚未开放"}
    assert response.headers["cache-control"] == "no-store"



def test_authorized_ai_test_is_opt_in_and_still_password_protected():
    app = FastAPI()

    @app.post("/api/chat/stream")
    def fake_no_model():
        return {"ok": True}

    app.add_middleware(
        PreviewGuard,
        username="preview",
        password="test-secret",
        allow_ai_post=True,
    )
    http = TestClient(app)
    assert http.post("/api/chat/stream").status_code == 401
    assert http.post(
        "/api/chat/stream", auth=("preview", "test-secret")
    ).json() == {"ok": True}
    assert http.post(
        "/api/not-an-ai-route", auth=("preview", "test-secret")
    ).status_code == 503
