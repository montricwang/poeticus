"""公网 AI 准入保护测试；不会连接真实 DeepSeek 或 PostgreSQL。"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import public_ai_guard


def make_app(monkeypatch, *, enabled=True, minute=5, daily=3, daily_result="ok"):
    monkeypatch.setenv("POETICUS_AI_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("POETICUS_AI_PER_IP_PER_MINUTE", str(minute))
    monkeypatch.setenv("POETICUS_AI_MAX_CONCURRENT", "2")
    monkeypatch.setenv("POETICUS_AI_DAILY_REQUESTS", str(daily))
    monkeypatch.setenv("POETICUS_AI_PER_IP_PER_DAY", "20")
    monkeypatch.setenv("POETICUS_AI_IP_HASH_SECRET", "testing-only-secret")
    monkeypatch.setenv("POETICUS_DATABASE_URL", "postgresql://fake/not-connected")

    reservations = []
    def fake_reserve(dsn, total_limit, per_ip_limit, day, client_hash):
        reservations.append((dsn, total_limit, per_ip_limit, day, client_hash))
        return daily_result

    monkeypatch.setattr(public_ai_guard, "_reserve_daily_slot", fake_reserve)
    app = FastAPI()

    @app.post("/api/chat/stream")
    def paid():
        return {"text": "synthetic, no model"}

    @app.post("/api/analyze")
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
    assert cli.post("/api/analyze", json={"poem": "test"}).status_code == 200
    assert len(spent) == 2
    assert all(x[1] == 3 for x in spent)


def test_per_peer_rate_limit_is_server_side(monkeypatch):
    cli, spent = make_app(monkeypatch, minute=1)
    assert cli.post("/api/chat/stream", json={"question": "x"}).status_code == 200
    second = cli.post("/api/chat/stream", json={"question": "x"})
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
    assert "每分钟最多提问 1 次" in second.json()["detail"]
    assert len(spent) == 1


def test_daily_budget_exhaustion_blocks_paid_routes(monkeypatch):
    cli, spent = make_app(monkeypatch, daily_result="global")
    response = cli.post("/api/chat/stream", json={"question": "x"})
    assert response.status_code == 429
    assert "今天大家的 AI 提问次数" in response.json()["detail"]
    assert "北京时间早上 8 点" in response.json()["detail"]
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


def test_ip_daily_quota_exhaustion_shows_distinct_message(monkeypatch):
    cli, spent = make_app(monkeypatch, daily_result="ip")
    response = cli.post("/api/analyze", json={"poem": "test"})
    assert response.status_code == 429
    assert "今天从这个网络发起的" in response.json()["detail"]
    assert "北京时间早上 8 点" in response.json()["detail"]
    assert len(spent) == 1
    assert cli.get("/api/poems").status_code == 200


def test_ip_daily_hash_differs_between_clients_and_days(monkeypatch):
    cli, spent = make_app(monkeypatch, minute=100)
    monkeypatch.setenv("POETICUS_TRUST_RAILWAY_REAL_IP", "true")
    # A fresh middleware instance reads the real-IP trust flag.
    cli, spent = make_app(monkeypatch, minute=100)
    # make_app constructs its middleware before the request is handled.
    assert cli.post("/api/analyze", json={"poem": "test"},
                    headers={"x-real-ip": "203.0.113.11"}).status_code == 200
    assert cli.post("/api/analyze", json={"poem": "test"},
                    headers={"x-real-ip": "203.0.113.12"}).status_code == 200
    assert spent[0][4] != spent[1][4]
    assert len(spent[0][4]) == 64
    assert "203.0.113" not in spent[0][4]


def test_missing_ip_hash_secret_fails_closed(monkeypatch):
    cli, spent = make_app(monkeypatch)
    monkeypatch.delenv("POETICUS_AI_IP_HASH_SECRET")
    # 原中间件已经初始化；新建应用才能重新读取环境变量。
    inner = FastAPI()
    @inner.post("/api/analyze")
    def paid():
        return {"ok": True}
    inner.add_middleware(public_ai_guard.PublicAIGuard)
    response = TestClient(inner).post("/api/analyze", json={"poem": "text"})
    assert response.status_code == 503
    assert spent == []


def test_atomic_quota_transaction_rolls_back_global_on_ip_limit(monkeypatch):
    """用合成 PostgreSQL 事务验证单 IP 超限不会误耗全站额度。"""
    class FakeDb:
        def __init__(self):
            self.global_used = 0
            self.per_ip = defaultdict(int)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @contextmanager
        def transaction(self):
            snapshot = (self.global_used, self.per_ip.copy())
            try:
                yield
            except BaseException:
                self.global_used, self.per_ip = snapshot
                raise

        def execute(self, statement, params):
            if "INSERT INTO ai_daily_quotas " in statement:
                _day, limit = params
                if self.global_used >= limit:
                    return FakeResult(None)
                self.global_used += 1
                return FakeResult((self.global_used,))
            if "INSERT INTO ai_ip_daily_quotas " in statement:
                _day, client_hash, limit = params
                if self.per_ip[client_hash] >= limit:
                    return FakeResult(None)
                self.per_ip[client_hash] += 1
                return FakeResult((self.per_ip[client_hash],))
            raise AssertionError("Unexpected SQL")

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

    db = FakeDb()
    monkeypatch.setattr(public_ai_guard.psycopg, "connect", lambda *_a, **_k: db)
    day = date(2026, 10, 4)
    reserve = public_ai_guard._reserve_daily_slot
    assert reserve("synthetic", 3, 2, day, "ip-A") == "ok"
    assert reserve("synthetic", 3, 2, day, "ip-A") == "ok"
    assert reserve("synthetic", 3, 2, day, "ip-A") == "ip"
    assert db.global_used == 2  # rejected client does not spend global budget
    assert reserve("synthetic", 3, 2, day, "ip-B") == "ok"
    assert reserve("synthetic", 3, 2, day, "ip-B") == "global"
    assert db.global_used == 3


def test_two_clients_share_total_but_have_separate_daily_quotas(monkeypatch):
    monkeypatch.setenv("POETICUS_TRUST_RAILWAY_REAL_IP", "true")
    cli, _spent = make_app(monkeypatch, minute=100, daily=200)
    counters = {"total": 0, "per_ip": defaultdict(int)}

    def fake_reserve(_dsn, total_limit, per_ip_limit, _day, client_hash):
        assert total_limit == 200
        assert per_ip_limit == 20
        if counters["total"] >= total_limit:
            return "global"
        if counters["per_ip"][client_hash] >= per_ip_limit:
            return "ip"
        counters["total"] += 1
        counters["per_ip"][client_hash] += 1
        return "ok"

    monkeypatch.setattr(public_ai_guard, "_reserve_daily_slot", fake_reserve)
    for _ in range(20):
        response = cli.post("/api/analyze", json={"poem": "text"},
                            headers={"x-real-ip": "203.0.113.11"})
        assert response.status_code == 200
    denied = cli.post("/api/analyze", json={"poem": "text"},
                      headers={"x-real-ip": "203.0.113.11"})
    assert denied.status_code == 429
    assert "今天从这个网络发起的" in denied.json()["detail"]
    other = cli.post("/api/analyze", json={"poem": "text"},
                     headers={"x-real-ip": "203.0.113.12"})
    assert other.status_code == 200
    assert counters["total"] == 21


def test_busy_is_distinct_from_minute_limit(monkeypatch):
    cli, spent = make_app(monkeypatch)
    monkeypatch.setattr(public_ai_guard.PublicAIGuard, "_acquire",
                        lambda self, client: (False, 5))
    response = cli.post("/api/chat/stream", json={"question": "test"})
    assert response.status_code == 429
    assert "正在处理另一条提问" in response.json()["detail"]
    assert response.headers["retry-after"] == "5"
    assert spent == []
