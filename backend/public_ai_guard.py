"""Small, fail-closed anonymous-AI guard for one Railway Web instance.

The durable daily allotment lives in PostgreSQL; a process-local sliding window
and active-request cap suppress bursts. No client-supplied X-Forwarded-For
header is trusted. The ASGI wrapper owns the whole SSE response lifetime.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock

import psycopg
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

AI_PATHS = frozenset({
    "/chat", "/api/chat", "/chat/stream", "/api/chat/stream",
    "/analyze", "/api/analyze",
})
MAX_REQUEST_BYTES = 48 * 1024


def _positive_env(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, 1), maximum)


def _reserve_daily_slot(dsn: str, limit: int) -> bool:
    """Atomic reservation in the existing DB, shared across restarts/instances.

    Missing table/unreachable database -> caller fails closed. Failed or
    client-aborted calls still consume a slot (conservative cost accounting).
    """
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
        row = conn.execute(
            """INSERT INTO ai_daily_quotas (day_utc, used_requests)
               VALUES (%s, 1)
               ON CONFLICT (day_utc)
               DO UPDATE SET used_requests = ai_daily_quotas.used_requests + 1
               WHERE ai_daily_quotas.used_requests < %s
               RETURNING used_requests""",
            (datetime.now(timezone.utc).date(), limit),
        ).fetchone()
        return row is not None


class PublicAIGuard:
    """Limit POST paid actions; public GET poems and /health stay unaffected."""

    def __init__(self, app) -> None:
        self.app = app
        # Explicitly opt into spending. Unset means read-only; PreviewGuard
        # remains an independent earlier deployment gate.
        self.enabled = os.getenv("POETICUS_AI_ENABLED", "").lower() == "true"
        # The Railway HTTPS edge documents X-Real-IP as its client IP
        # header. Only trust it in an explicitly Railway-only deployment.
        self.trust_railway_real_ip = (
            os.getenv("POETICUS_TRUST_RAILWAY_REAL_IP", "").lower() == "true"
        )
        self.per_minute = _positive_env("POETICUS_AI_PER_IP_PER_MINUTE", 5, 100)
        self.concurrent = _positive_env("POETICUS_AI_MAX_CONCURRENT", 2, 16)
        self.daily = _positive_env("POETICUS_AI_DAILY_REQUESTS", 60, 10000)
        self.lock = Lock()
        self.active = 0
        self.windows: dict[str, deque[float]] = defaultdict(deque)

    async def _reject(self, scope, receive, send, status: int, detail: str, retry: int | None = None):
        headers = {"Cache-Control": "no-store"}
        if retry is not None:
            headers["Retry-After"] = str(retry)
        await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)

    def _acquire(self, client: str) -> tuple[bool, int]:
        """Reserve process concurrency and per-peer window in one short lock."""
        now = time.monotonic()
        with self.lock:
            times = self.windows[client]
            while times and times[0] <= now - 60:
                times.popleft()
            if len(times) >= self.per_minute:
                return False, 60
            if self.active >= self.concurrent:
                return False, 5
            times.append(now)
            self.active += 1
            return True, 0

    def _release(self) -> None:
        with self.lock:
            self.active -= 1

    def _client_identity(self, scope) -> str:
        peer = str((scope.get("client") or ("unknown", 0))[0])
        if not self.trust_railway_real_ip:
            return peer
        values = [
            value for key, value in scope.get("headers", [])
            if key.lower() == b"x-real-ip"
        ]
        if len(values) != 1:
            return peer
        try:
            address = values[0].decode("ascii")
            return str(ipaddress.ip_address(address))
        except (UnicodeDecodeError, ValueError):
            return peer

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") not in AI_PATHS:
            await self.app(scope, receive, send)
            return

        if not self.enabled:
            await self._reject(scope, receive, send, 503, "AI 生成尚未开放")
            return

        # Limit the entire incoming body, including chunked requests without
        # Content-Length, before paying for a model call or parsing Pydantic.
        buffered = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            size += len(message.get("body", b""))
            if size > MAX_REQUEST_BYTES:
                await self._reject(scope, receive, send, 413, "请求内容过长")
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if buffered:
                return buffered.pop(0)
            return await receive()

        # Never use anonymous, potentially spoofed X-Forwarded-For values.
        # Railway X-Real-IP is only used when the operator opts in.
        client = self._client_identity(scope)
        ok, retry = self._acquire(client)
        if not ok:
            await self._reject(scope, replay_receive, send, 429, "请求过于频繁，请稍后再试", retry)
            return
        try:
            dsn = os.getenv("POETICUS_DATABASE_URL")
            if not dsn:
                await self._reject(scope, replay_receive, send, 503, "AI 预算服务不可用")
                return
            try:
                budget_ok = await asyncio.to_thread(_reserve_daily_slot, dsn, self.daily)
            except psycopg.Error:
                logger.warning("AI budget store unavailable")
                await self._reject(scope, replay_receive, send, 503, "AI 预算服务暂时不可用")
                return
            if not budget_ok:
                await self._reject(scope, replay_receive, send, 429, "今日 AI 体验额度已用完", 3600)
                return
            # Holds concurrency until StreamingResponse is done/disconnected.
            await self.app(scope, replay_receive, send)
        finally:
            self._release()
