"""Temporary Basic Auth + read-only guard for the first cloud smoke test.

Enable only when POETICUS_PREVIEW_PASSWORD is provided on the server.
This is NOT the public site's final authentication/abuse protection.
"""
from __future__ import annotations

import base64
import binascii
import hmac

from starlette.responses import JSONResponse, PlainTextResponse


class PreviewGuard:
    """One lightweight ASGI gate in front of static assets and all app routes."""

    def __init__(self, app, *, username: str, password: str) -> None:
        if not password:
            raise ValueError("A preview password is required")
        self.app = app
        self.username = username
        self.password = password

    def _authorized(self, scope) -> bool:
        headers = dict(scope.get("headers", []))
        value = headers.get(b"authorization", b"")
        if not value.startswith(b"Basic "):
            return False
        try:
            raw = base64.b64decode(value[6:], validate=True)
            user, password = raw.decode("utf-8").split(":", 1)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
        return hmac.compare_digest(user, self.username) and hmac.compare_digest(
            password, self.password
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Railway's health probe does not send credentials.
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        if not self._authorized(scope):
            response = PlainTextResponse(
                "Poeticus private preview: sign in to continue.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Poeticus Preview"'},
            )
            await response(scope, receive, send)
            return

        # The test preview can read synthetic works, never spend model tokens.
        if scope.get("method") not in {"GET", "HEAD"}:
            response = JSONResponse(
                {"detail": "当前为只读测试预览，AI 问答尚未开放"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
