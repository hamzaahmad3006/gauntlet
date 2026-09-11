"""Build a transport for a target row: decrypt its connection blob inside the worker only, run SSRF
validation (validate at registration, re-resolve at connection time), and construct the adapter."""

from __future__ import annotations

from typing import Any

from gauntlet.caller.adapters.base import Transport, TransportError
from gauntlet.caller.adapters.websocket_pcm import WebSocketPCMTransport
from gauntlet.common import urlguard
from gauntlet.common.crypto import decrypt_json


def connection_of(target: dict[str, Any], key: bytes) -> dict[str, Any]:
    try:
        return decrypt_json(key, target["connection_encrypted"], target["connection_nonce"])
    except Exception:
        raise TransportError("auth_failed", "connection credentials could not be decrypted; re-enter them") from None


def make_transport(target: dict[str, Any], key: bytes, environment: str, call_id: str,
                   nonce: str | None = None) -> Transport:
    conn = connection_of(target, key)
    if target["adapter"] == "websocket_pcm":
        url = conn["url"]
        if not target.get("bundled"):
            try:
                v = urlguard.validate(url, environment)
                urlguard.recheck(v, environment)
            except urlguard.SSRFBlocked as e:
                raise TransportError("connect_failed", f"ssrf_blocked: {e}") from None
        return WebSocketPCMTransport(url, token=conn.get("token"), headers=conn.get("headers"), nonce=nonce)
    if target["adapter"] == "livekit":
        from gauntlet.caller.adapters.livekit import LiveKitTransport

        return LiveKitTransport(url=conn["url"], api_key=conn["api_key"], api_secret=conn["api_secret"],
                                room=conn.get("room", "gauntlet-{call_id}").replace("{call_id}", call_id),
                                identity=f"gauntlet-caller-{call_id}")
    raise TransportError("protocol_error", f"unknown adapter {target['adapter']}")


def validate_connection(adapter: str, conn: dict[str, Any], environment: str) -> str:
    """Registration-time validation. Returns a masked, display-only hint."""
    from gauntlet.middleware.errors import ApiError

    if adapter == "websocket_pcm":
        url = str(conn.get("url") or "")
        if not url:
            raise ApiError(422, "validation_failed", "connection.url is required", "/connection/url")
        try:
            urlguard.validate(url, environment)
        except urlguard.SSRFBlocked as e:
            raise ApiError(422, "ssrf_blocked", f"target URL rejected ({e.host_class})", "/connection/url",
                           extra={"host_class": e.host_class}) from None
        if len(str(conn)) > 16 * 1024:
            raise ApiError(422, "validation_failed", "connection blob exceeds 16 KB", "/connection")
        return url.split("?")[0]
    if adapter == "livekit":
        for f in ("url", "api_key", "api_secret"):
            if not conn.get(f):
                raise ApiError(422, "validation_failed", f"connection.{f} is required", f"/connection/{f}")
        if not str(conn["url"]).startswith("wss://"):
            raise ApiError(422, "validation_failed", "LiveKit URL must use wss://", "/connection/url")
        room = str(conn.get("room", "gauntlet-{call_id}"))
        import re

        if not re.fullmatch(r"[A-Za-z0-9_.\-{}]{1,128}", room):
            raise ApiError(422, "validation_failed", "room name must match ^[A-Za-z0-9_.-]{1,128}$", "/connection/room")
        return f"{conn['url']} · key {str(conn['api_key'])[:4]}••••"
    raise ApiError(422, "validation_failed", "unknown adapter", "/adapter")
