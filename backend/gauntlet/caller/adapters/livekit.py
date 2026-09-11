"""ARC-020 LiveKit room adapter — real WebRTC media (SRS-FR-011, SRS 12.3).

The worker joins the target's room as an ordinary participant (a caller *is* a participant), publishes
one mono 16 kHz track and subscribes to the first remote audio track. The SDK resamples and runs Opus
and its jitter buffer; frames are delivered at 16 kHz in 20 ms blocks and timestamped on arrival.
The outbound source queue is kept short (100 ms) so the SDK adds as little buffering as possible to the
caller's transmit timeline; that buffering is part of the rig pipeline and is not covered by the loopback
calibration bound (docs/LIMITATIONS.md).

Requires ``pip install "backend[livekit]"``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import numpy as np

from gauntlet.caller.adapters.base import Transport, TransportError
from gauntlet.common.clock import now_ns
from gauntlet.media.audio import FRAME_SAMPLES, SAMPLE_RATE

TRACK_WAIT_TIMEOUT_S = 20.0


class LiveKitTransport(Transport):
    name = "livekit"

    def __init__(self, url: str, api_key: str, api_secret: str, room: str, identity: str,
                 track_wait_s: float = TRACK_WAIT_TIMEOUT_S):
        super().__init__()
        self.url, self.api_key, self.api_secret = url, api_key, api_secret
        self.room_name, self.identity, self.track_wait_s = room, identity, track_wait_s
        self._room: Any = None
        self._source: Any = None
        self._queue: asyncio.Queue[tuple[np.ndarray, int] | None] = asyncio.Queue(maxsize=500)
        self._remote_track: asyncio.Future[Any] | None = None
        self._reader: asyncio.Task[None] | None = None
        self._closed = False
        self.bye_reason: str | None = None

    async def connect(self) -> None:
        try:
            from livekit import api, rtc
        except ImportError:  # pragma: no cover - optional dependency
            raise TransportError("connect_failed", "livekit SDK not installed (backend[livekit])") from None
        t0 = now_ns()
        token = (api.AccessToken(self.api_key, self.api_secret).with_identity(self.identity)
                 .with_name("GAUNTLET synthetic caller")
                 .with_grants(api.VideoGrants(room_join=True, room=self.room_name, can_publish=True, can_subscribe=True))
                 .to_jwt())
        loop = asyncio.get_running_loop()
        self._remote_track = loop.create_future()
        self._room = rtc.Room(loop=loop)

        @self._room.on("track_subscribed")
        def _on_track(track: Any, publication: Any, participant: Any) -> None:  # noqa: ARG001
            if track.kind == rtc.TrackKind.KIND_AUDIO and self._remote_track and not self._remote_track.done():
                self._remote_track.set_result(track)

        @self._room.on("disconnected")
        def _on_disc(*_: Any) -> None:
            if not self._closed:
                self.bye_reason = "transport_disconnected"
                with contextlib.suppress(asyncio.QueueFull):
                    self._queue.put_nowait(None)

        try:
            await asyncio.wait_for(self._room.connect(self.url, token), 20)
        except asyncio.TimeoutError:
            raise TransportError("connect_failed", "LiveKit connect timed out") from None
        except Exception as e:
            msg = str(e).lower()
            code = "auth_failed" if ("401" in msg or "unauthorized" in msg or "token" in msg) else "connect_failed"
            raise TransportError(code, f"{type(e).__name__}: {e}") from None
        self._source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=100)
        track = rtc.LocalAudioTrack.create_audio_track("gauntlet-caller", self._source)
        opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self._room.local_participant.publish_track(track, opts)
        # an agent that is already in the room: subscribe to its existing audio track
        for p in self._room.remote_participants.values():
            for pub in p.track_publications.values():
                if pub.track is not None and pub.kind == rtc.TrackKind.KIND_AUDIO and not self._remote_track.done():
                    self._remote_track.set_result(pub.track)
        try:
            remote = await asyncio.wait_for(self._remote_track, self.track_wait_s)
        except asyncio.TimeoutError:
            await self.close("no_remote_audio")
            raise TransportError("no_remote_audio", f"no remote audio track within {self.track_wait_s:.0f} s") from None
        self.connect_ms = (now_ns() - t0) / 1e6
        stream = rtc.AudioStream(remote, sample_rate=SAMPLE_RATE, num_channels=1, frame_size_ms=20)
        self._reader = asyncio.create_task(self._read(stream))

    async def _read(self, stream: Any) -> None:
        pending = np.zeros(0, dtype=np.int16)
        try:
            async for ev in stream:
                t = now_ns()
                data = np.frombuffer(bytes(ev.frame.data), dtype=np.int16)
                pending = np.concatenate([pending, data])
                while len(pending) >= FRAME_SAMPLES:
                    frame, pending = pending[:FRAME_SAMPLES].copy(), pending[FRAME_SAMPLES:]
                    try:
                        self._queue.put_nowait((frame, t))
                    except asyncio.QueueFull:
                        self.stats["rx_overflow"] = self.stats.get("rx_overflow", 0) + 1
        except asyncio.CancelledError:
            pass
        finally:
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(None)

    async def send_frame(self, frame: np.ndarray) -> None:
        if self._closed or self._source is None:
            return
        from livekit import rtc

        await self._source.capture_frame(rtc.AudioFrame(frame.astype(np.int16).tobytes(), SAMPLE_RATE, 1, len(frame)))

    async def frames(self) -> AsyncIterator[tuple[np.ndarray, int]]:  # type: ignore[override]
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def close(self, reason: str = "done") -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader:
            self._reader.cancel()
        with contextlib.suppress(Exception):
            if self._room is not None:
                await asyncio.wait_for(self._room.disconnect(), 5)
