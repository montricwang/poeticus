"""Railway 单实例的匿名 AI 保护中间件。

每日额度持久化在 PostgreSQL；进程内滑动窗口与并发计数抑制突发请求。
默认不信任客户端提供的 X-Forwarded-For；ASGI 中间件覆盖整个 SSE 生命周期。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
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


class _PerIpDailyLimit(Exception):
    """调用方日额度耗尽时，用异常触发全站额度事务回滚。"""


def _reserve_daily_slot(
    dsn: str, total_limit: int, per_ip_limit: int, day, client_hash: str
) -> str:
    """在一个 PostgreSQL 事务里同时占用全站和单 IP 的 UTC 日额度。

    返回 "ok"、"global" 或 "ip"。单 IP 超限时不能消耗全站额度；
    已经进入模型调用后，即使失败或中断，也视为消耗本次额度。
    """
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
        try:
            with conn.transaction():
                global_row = conn.execute(
                    """INSERT INTO ai_daily_quotas (day_utc, used_requests)
                       VALUES (%s, 1)
                       ON CONFLICT (day_utc)
                       DO UPDATE SET used_requests = ai_daily_quotas.used_requests + 1
                       WHERE ai_daily_quotas.used_requests < %s
                       RETURNING used_requests""",
                    (day, total_limit),
                ).fetchone()
                if global_row is None:
                    return "global"

                ip_row = conn.execute(
                    """INSERT INTO ai_ip_daily_quotas (day_utc, client_hash, used_requests)
                       VALUES (%s, %s, 1)
                       ON CONFLICT (day_utc, client_hash)
                       DO UPDATE SET used_requests = ai_ip_daily_quotas.used_requests + 1
                       WHERE ai_ip_daily_quotas.used_requests < %s
                       RETURNING used_requests""",
                    (day, client_hash, per_ip_limit),
                ).fetchone()
                if ip_row is None:
                    raise _PerIpDailyLimit()
        except _PerIpDailyLimit:
            return "ip"
    return "ok"

class PublicAIGuard:
    """限制会产生模型费用的 POST 请求，不影响公开作品读取与 /health。"""

    def __init__(self, app) -> None:
        self.app = app
        # 只有显式开启才允许产生模型费用；未开启时保持只读。
        self.enabled = os.getenv("POETICUS_AI_ENABLED", "").lower() == "true"
        # Railway HTTPS 边缘会提供 X-Real-IP；只有明确处于 Railway
        # 信任边界内时才读取这个头。
        self.trust_railway_real_ip = (
            os.getenv("POETICUS_TRUST_RAILWAY_REAL_IP", "").lower() == "true"
        )
        self.per_minute = _positive_env("POETICUS_AI_PER_IP_PER_MINUTE", 5, 100)
        self.concurrent = _positive_env("POETICUS_AI_MAX_CONCURRENT", 2, 16)
        self.daily = _positive_env("POETICUS_AI_DAILY_REQUESTS", 60, 10000)
        self.per_ip_daily = _positive_env("POETICUS_AI_PER_IP_PER_DAY", 20, 1000)
        self.ip_hash_secret = os.getenv("POETICUS_AI_IP_HASH_SECRET", "")
        self.lock = Lock()
        self.active = 0
        self.windows: dict[str, deque[float]] = defaultdict(deque)

    async def _reject(self, scope, receive, send, status: int, detail: str, retry: int | None = None):
        headers = {"Cache-Control": "no-store"}
        if retry is not None:
            headers["Retry-After"] = str(retry)
        await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)

    def _acquire(self, client: str) -> tuple[bool, int]:
        """在一次短锁内同时占用进程并发位与客户端分钟窗口。"""
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

        # 在解析 Pydantic 或产生模型费用前限制完整请求体；
        # 即使请求没有 Content-Length、采用分块传输，也必须累计检查。
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

        # 不使用匿名客户端可伪造的 X-Forwarded-For。
        # 只有部署者显式开启信任时才使用 Railway 的 X-Real-IP。
        client = self._client_identity(scope)
        ok, retry = self._acquire(client)
        if not ok:
            await self._reject(
                scope, replay_receive, send, 429,
                (
                    f"稍等一会儿，刚才的提问有点密集。每分钟最多提问 {self.per_minute} 次，"
                    "约一分钟后就能继续聊了。"
                    if retry == 60 else
                    "AI 伴读正在处理另一条提问，稍等片刻就能继续聊了。"
                ),
                retry,
            )
            return
        try:
            dsn = os.getenv("POETICUS_DATABASE_URL")
            if not dsn or not self.ip_hash_secret:
                await self._reject(scope, replay_receive, send, 503, "AI 预算服务不可用")
                return
            day = datetime.now(timezone.utc).date()
            client_hash = hmac.new(
                self.ip_hash_secret.encode("utf-8"),
                f"{day.isoformat()}:{client}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            try:
                result = await asyncio.to_thread(
                    _reserve_daily_slot, dsn, self.daily, self.per_ip_daily,
                    day, client_hash,
                )
            except psycopg.Error:
                logger.warning("AI budget store unavailable")
                await self._reject(scope, replay_receive, send, 503, "AI 预算服务暂时不可用")
                return
            if result == "global":
                await self._reject(
                    scope, replay_receive, send, 429,
                    "今天大家的 AI 提问次数已经用完了，每天北京时间早上 8 点恢复。"
                    "诗词还可以照常阅读，等额度恢复后再接着聊吧。",
                    3600,
                )
                return
            if result == "ip":
                await self._reject(
                    scope, replay_receive, send, 429,
                    "今天从这个网络发起的 AI 提问次数已经用完了，"
                    "每天北京时间早上 8 点恢复。诗词还可以照常阅读。",
                    3600,
                )
                return
            # 并发位一直占用到 StreamingResponse 完成或连接断开。
            await self.app(scope, replay_receive, send)
        finally:
            self._release()
