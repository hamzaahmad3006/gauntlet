"""Transport-agnostic fixture session speaking ``gauntlet.pcm.v1``.

Modes (selected per connection by query parameters, so one server can pose as many "configurations"):

``calibration`` — detects the end of the caller's tone at sample resolution, waits exactly ``delay_ms``
on the shared clock, then emits a response tone of ``response_ms``. It reports the instant the response's
first sample was sent as a ``marker`` message: that instant is the calibration ground truth (D-19).

``agent`` — a programmable synthetic voice agent. Energy VAD endpointing with an ``endpoint_ms`` silence
window, then a ``delay_ms`` processing delay, then a speech-shaped response line. On barge-in it stops
``yield_ms`` after the caller starts speaking, or never if ``yield_ms`` is absent. Every knob is a
latency or turn-taking behaviour the rig must measure, which makes this the rig's own test subject.

``echo`` — replays the caller's last utterance after endpointing (diagnostic audio-in/audio-out check).

Output is paced on an absolute 20 ms schedule and response audio is anchored to absolute time, so the
emitted audio does not inherit the pacing loop's scheduling jitter.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from gauntlet.caller.local_synth import babble
from gauntlet.common.clock import now_ns
from gauntlet.media.audio import FRAME_NS, FRAME_SAMPLES, SAMPLE_NS, db_to_amplitude, from_bytes, tone, to_bytes
from gauntlet.media.probe import Probe, ProbeConfig

PROTOCOL = "gauntlet.pcm.v1"

AGENT_SCRIPT = [
    "Thank you for calling Bella Tavola. How can I help you today?",
    "Of course. What day and time would you like, and for how many people?",
    "Lovely. And what name should I put the booking under?",
    "Perfect. I have that booked for you. Is there anything else I can help with?",
    "Sure, no problem at all.",
    "Thanks for calling Bella Tavola. Goodbye!",
]


@dataclass
class FixtureConfig:
    mode: str = "calibration"
    delay_ms: float = 500.0
    response_ms: float = 400.0
    yield_ms: float | None = None
    endpoint_ms: float = 500.0
    greeting: bool = False
    tone_hz: float = 1000.0
    level_db: float = -14.0
    voice: str = "fixture-agent"
    rate: float = 1.0

    @classmethod
    def from_query(cls, query: dict[str, str]) -> FixtureConfig:
        cfg = cls()
        types = {f.name: f.type for f in fields(cls)}
        for k, v in query.items():
            if k not in types:
                continue
            if k == "mode":
                if v not in ("calibration", "agent", "echo"):
                    raise ValueError(f"unknown fixture mode {v!r}")
                cfg.mode = v
            elif k == "greeting":
                cfg.greeting = v.lower() in ("1", "true", "yes")
            elif k == "voice":
                cfg.voice = v[:64]
            elif k == "yield_ms":
                cfg.yield_ms = None if v.lower() in ("", "none", "never") else float(v)
            else:
                setattr(cfg, k, float(v))
        cfg.delay_ms = min(max(cfg.delay_ms, 0.0), 10_000.0)
        cfg.endpoint_ms = min(max(cfg.endpoint_ms, 60.0), 3000.0)
        cfg.response_ms = min(max(cfg.response_ms, 20.0), 30_000.0)
        return cfg


class _Track:
    """Response audio anchored to an absolute start time on the shared clock."""

    def __init__(self, pcm: np.ndarray, start_ns: int, label: str):
        self.pcm = pcm
        self.start_ns = start_ns
        self.stop_ns: int | None = None
        self.label = label
        self.started_reported = False
        self.actual_start_ns: int | None = None


class FixtureSession:
    def __init__(self, cfg: FixtureConfig, send_bytes: Callable[[bytes], Awaitable[None]],
                 send_text: Callable[[str], Awaitable[None]]):
        self.cfg = cfg
        self._send_bytes = send_bytes
        self._send_text = send_text
        self._track: _Track | None = None
        self._pending: tuple[int, str] | None = None  # (start_ns, label) not yet rendered
        self._turn = 0
        self._stop = asyncio.Event()
        self._markers: list[dict[str, Any]] = []
        self._amp_thr = db_to_amplitude(-40.0)
        self._tone_active = False
        self._tone_last_ns: int | None = None
        endpoint_frames = max(3, round(cfg.endpoint_ms / 20))
        self._probe = Probe(ProbeConfig(offset_frames=endpoint_frames))
        self._echo_buf: list[np.ndarray] = []
        self._echo_last: np.ndarray | None = None
        self.hello: dict[str, Any] | None = None

    # -- protocol ---------------------------------------------------------------------------------
    async def on_text(self, text: str) -> bool:
        """Returns False when the peer said bye."""
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return True
        if msg.get("type") == "hello":
            self.hello = msg
            await self._send_text(json.dumps({"type": "hello", "protocol": PROTOCOL, "nonce": msg.get("nonce"),
                                              "fixture": self.cfg.mode, "sample_rate": 16000, "frame_ms": 20}))
            if self.cfg.greeting and self.cfg.mode == "agent":
                self._schedule(now_ns() + 300 * 1_000_000, "greeting")
        elif msg.get("type") == "bye":
            self._stop.set()
            return False
        return True

    def on_frame(self, data: bytes, t_recv_ns: int) -> None:
        if len(data) != FRAME_SAMPLES * 2:
            return
        frame = from_bytes(data)
        if self.cfg.mode == "calibration":
            self._on_calibration_frame(frame, t_recv_ns)
        else:
            self._on_agent_frame(frame, t_recv_ns)

    def stop(self) -> None:
        self._stop.set()

    # -- input ------------------------------------------------------------------------------------
    def _barge_in(self, onset_ns: int) -> None:
        tr = self._track
        if tr is None or tr.stop_ns is not None:
            if self._pending is not None and self._pending[0] > onset_ns:
                self._pending = None  # caller resumed before we committed: wait for them
            return
        playing = tr.start_ns <= onset_ns < tr.start_ns + int(len(tr.pcm) * SAMPLE_NS)
        if playing and self.cfg.yield_ms is not None:
            tr.stop_ns = onset_ns + int(self.cfg.yield_ms * 1_000_000)

    def _on_calibration_frame(self, frame: np.ndarray, t: int) -> None:
        hits = np.nonzero(np.abs(frame.astype(np.int32)) > self._amp_thr)[0]
        if hits.size:
            if not self._tone_active:
                self._tone_active = True
                self._barge_in(t + int(round(hits[0] * SAMPLE_NS)))
            self._tone_last_ns = t + int(round((hits[-1] + 1) * SAMPLE_NS))
            if hits[-1] < FRAME_SAMPLES - 24:  # tone ended inside this frame
                self._tone_ended()
        elif self._tone_active:
            self._tone_ended()

    def _tone_ended(self) -> None:
        self._tone_active = False
        if self._tone_last_ns is None:
            return
        start = self._tone_last_ns + int(self.cfg.delay_ms * 1_000_000)
        self._schedule(start, "calibration_response", trigger_ns=self._tone_last_ns)

    def _on_agent_frame(self, frame: np.ndarray, t: int) -> None:
        for ev in self._probe.process(frame, t):
            if ev.kind == "speech_onset":
                self._echo_buf = []
                self._barge_in(ev.t_ns)
            else:
                commit = ev.t_ns + int((self.cfg.endpoint_ms + self.cfg.delay_ms) * 1_000_000)
                if self.cfg.mode == "echo":
                    self._echo_last = np.concatenate(self._echo_buf) if self._echo_buf else None
                self._schedule(commit, "echo" if self.cfg.mode == "echo" else "reply", trigger_ns=ev.t_ns)
        if self._probe.speaking and self.cfg.mode == "echo":
            self._echo_buf.append(frame.copy())

    def _schedule(self, start_ns: int, label: str, trigger_ns: int | None = None) -> None:
        self._pending = (start_ns, label)
        if trigger_ns is not None:
            self._markers.append({"type": "marker", "kind": "trigger", "label": label, "t_ns": trigger_ns,
                                  "scheduled_ns": start_ns})

    def _response_pcm(self, label: str) -> np.ndarray:
        c = self.cfg
        if c.mode == "calibration":
            return tone(c.tone_hz, c.response_ms, c.level_db)
        if label == "echo":
            return self._echo_last if self._echo_last is not None else tone(440, 300, -20)
        if label == "greeting":
            line = AGENT_SCRIPT[0]
            self._turn = 1
        else:
            idx = max(1, self._turn)
            line = AGENT_SCRIPT[min(idx, len(AGENT_SCRIPT) - 1)]
            self._turn = idx + 1
        return babble(line, c.voice, c.rate)

    # -- output -----------------------------------------------------------------------------------
    def _render(self, now: int) -> np.ndarray:
        if self._pending is not None and self._pending[0] < now + FRAME_NS:
            start, label = self._pending
            self._pending = None
            self._track = _Track(self._response_pcm(label), start, label)
        tr = self._track
        out = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        if tr is None:
            return out
        start_idx = int(round((now - tr.start_ns) / SAMPLE_NS))
        stop_idx = len(tr.pcm)
        if tr.stop_ns is not None:
            stop_idx = min(stop_idx, max(0, int(round((tr.stop_ns - tr.start_ns) / SAMPLE_NS))))
        a, b = max(start_idx, 0), min(start_idx + FRAME_SAMPLES, stop_idx)
        if b > a:
            out[a - start_idx : b - start_idx] = tr.pcm[a:b]
            if not tr.started_reported:
                tr.started_reported = True
                tr.actual_start_ns = now + int(round((a - start_idx) * SAMPLE_NS))
                self._markers.append({"type": "marker", "kind": "response_start", "label": tr.label,
                                      "t_ns": tr.actual_start_ns, "scheduled_ns": tr.start_ns,
                                      "late_ns": tr.actual_start_ns - tr.start_ns})
        if start_idx + FRAME_SAMPLES >= stop_idx:
            end_ns = now + int(round((stop_idx - start_idx) * SAMPLE_NS))
            self._markers.append({"type": "marker", "kind": "response_end", "label": tr.label, "t_ns": end_ns,
                                  "yielded": tr.stop_ns is not None and stop_idx < len(tr.pcm)})
            self._track = None
        return out

    async def pace(self) -> None:
        t0 = now_ns()
        i = 0
        while not self._stop.is_set():
            target = t0 + i * FRAME_NS
            now = now_ns()
            if target > now:
                await asyncio.sleep((target - now) / 1e9)
                now = now_ns()
            elif now - target > 2 * FRAME_NS:  # stalled: resynchronise rather than burst to catch up
                t0 += (now - target) // FRAME_NS * FRAME_NS
                target = t0 + i * FRAME_NS
            frame = self._render(now)
            try:
                await self._send_bytes(to_bytes(frame))
                while self._markers:
                    await self._send_text(json.dumps(self._markers.pop(0)))
            except Exception:
                self._stop.set()
                return
            i += 1
