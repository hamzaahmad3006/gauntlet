"""ARC-021 WebSocket PCM adapter — protocol ``gauntlet.pcm.v1`` (SRS-FR-012, SRS 12.4, docs/ADAPTERS.md).

Client sends a JSON hello, then binary frames of 320 samples (640 bytes) of 16 kHz mono s16le, one
per 20 ms. The server streams frames back in the same shape. JSON text frames carry control messages
(hello, bye, and optional ``marker`` messages that only fixtures emit). The same protocol is served by
the calibration target (deviation D-04), so this path is exercised by every calibration run.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import websockets

from gauntlet.caller.adapters.base import Transport, TransportError
from gauntlet.common.clock import now_ns
from gauntlet.media.audio import FRAME_BYTES, from_bytes, to_bytes

PROTOCOL = "gauntlet.pcm.v1"
MAX_MALFORMED_FRAMES = 10


class WebSocketPCMTransport(Transport):
    name = "websocket_pcm"

    def __init__(self, url: str, token: str | None = None, headers: dict[str, str] | None = None,
                 nonce: str | None = None, connect_timeout_s: float = 20.0):
        super().__init__()
        self.url = url
        self.token = token
        self.headers = dict(headers or {})
        self.nonce = nonce or secrets.token_hex(16)
        self.connect_timeout_s = connect_timeout_s
        self.server_hello: dict[str, Any] | None = None
        self._ws: Any = None
        self._queue: asyncio.Queue[tuple[np.ndarray, int] | None] = asyncio.Queue(maxsize=500)
        self._reader: asyncio.Task[None] | None = None
        self._malformed = 0
        self._closed = False
        self.bye_reason: str | None = None

    async def connect(self) -> None:
        hdrs = dict(self.headers)
        if self.token:
            hdrs["Authorization"] = f"Bearer {self.token}"
        t0 = now_ns()
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(self.url, additional_headers=hdrs or None, max_size=2**20,
                                   open_timeout=self.connect_timeout_s, ping_interval=20, compression=None),
                timeout=self.connect_timeout_s,
            )
            hello = {"type": "hello", "protocol": PROTOCOL, "sample_rate": 16000, "frame_ms": 20, "nonce": self.nonce}
            await self._ws.send(json.dumps(hello))
            while True:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=self.connect_timeout_s)
                if isinstance(msg, str):
                    data = json.loads(msg)
                    if data.get("type") == "hello":
                        if data.get("protocol") != PROTOCOL:
                            raise TransportError("protocol_error", f"server protocol {data.get('protocol')!r}")
                        self.server_hello = data
                        break
                # audio before hello is tolerated and dropped
        except TransportError:
            raise
        except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as e:
            raise TransportError("connect_failed", f"{type(e).__name__}: {e}") from None
        self.connect_ms = (now_ns() - t0) / 1e6
        self._reader = asyncio.create_task(self._read_loop(), name="ws-pcm-reader")

    async def _read_loop(self) -> None:
        try:
            async for msg in self._ws:
                t = now_ns()
                if isinstance(msg, (bytes, bytearray)):
                    n = len(msg)
                    if n == 0 or n % FRAME_BYTES:
                        self._malformed += 1
                        if self._malformed > MAX_MALFORMED_FRAMES:
                            self.bye_reason = "protocol_error"
                            break
                        continue
                    for off in range(0, n, FRAME_BYTES):
                        frame = from_bytes(bytes(msg[off : off + FRAME_BYTES]))
                        try:
                            self._queue.put_nowait((frame, t))
                        except asyncio.QueueFull:
                            self.stats["rx_overflow"] = self.stats.get("rx_overflow", 0) + 1
                else:
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        self._malformed += 1
                        continue
                    kind = data.get("type")
                    if kind == "marker":
                        data["t_recv_ns"] = t
                        self.markers.put_nowait(data)
                    elif kind == "bye":
                        self.bye_reason = str(data.get("reason", "bye"))
                        break
        except websockets.exceptions.ConnectionClosed:
            if not self._closed:
                self.bye_reason = self.bye_reason or "transport_disconnected"
        finally:
            await self._queue.put(None)

    async def send_frame(self, frame: np.ndarray) -> None:
        if self._closed or self._ws is None:
            return
        try:
            await self._ws.send(to_bytes(frame))
        except websockets.exceptions.ConnectionClosed:
            if not self._closed:
                raise TransportError("transport_disconnected", "peer closed during send") from None

    async def frames(self) -> AsyncIterator[tuple[np.ndarray, int]]:  # type: ignore[override]
        while True:
            item = await self._queue.get()
            if item is None:
                if self.bye_reason == "protocol_error":
                    raise TransportError("protocol_error", f"more than {MAX_MALFORMED_FRAMES} malformed frames")
                return
            yield item

    async def close(self, reason: str = "done") -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._ws is not None:
                try:
                    await asyncio.wait_for(self._ws.send(json.dumps({"type": "bye", "reason": reason})), 2)
                except Exception:
                    pass
                await asyncio.wait_for(self._ws.close(code=1000), 3)
        except Exception:
            pass
        if self._reader:
            self._reader.cancel()
        self.stats["malformed_frames"] = self._malformed
