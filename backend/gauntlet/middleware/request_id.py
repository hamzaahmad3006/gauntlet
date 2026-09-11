"""Correlation id on every request and log line (SRS-NFR-035). Pure ASGI so streaming responses (SSE)
are never buffered."""

from __future__ import annotations

import contextvars
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_cid: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def current_correlation_id() -> str:
    return _cid.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, version: str = "dev"):
        self.app = app
        self.version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-correlation-id", b"").decode()[:64]
        cid = incoming if incoming and incoming.replace("-", "").isalnum() else secrets.token_hex(8)
        token = _cid.set(cid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-correlation-id", cid.encode()))
                headers.append((b"x-gauntlet-version", self.version.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _cid.reset(token)
