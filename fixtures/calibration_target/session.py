"""Transport-agnostic fixture session speaking ``gauntlet.pcm.v1``.

Modes (selected per connection by query parameters, so one server can pose as many "configurations"):

``calibration`` — detects the end of the caller's tone at sample resolution, waits exactly ``delay_ms``
on the shared clock, then emits a response tone of ``response_ms``. It reports the instant the response's
first sample was sent as a ``marker`` message: that instant is the calibration ground truth (D-19).

``agent`` — a programmable synthetic voice agent. Energy VAD endpointing with an ``endpoint_ms`` silence
window, then a ``delay_ms`` processing delay, then a speech-shaped response line. On barge-in it stops
``yield_ms`` after the caller starts speaking, or never if ``yield_ms`` is absent. Every knob is a
latency or turn-taking behaviour the rig must measure, which makes this the rig's own test subject.

``silent`` — accepts the connection and the caller's audio but never speaks (diagnostic TC-014).

``echo`` — replays the caller's last utterance after endpointing (diagnostic audio-in/audio-out check).

``reference`` — the reference agent (fixtures/reference_agent): the same endpointing and barge-in knobs,
but replies come from a real pipeline — Groq Whisper speech-to-text, a Groq language model chosen by
``model``, and ElevenLabs or espeak speech. ``delay_ms`` becomes a floor. Without a Groq key it behaves
like ``agent``.

Output is paced on an absolute 20 ms schedule and response audio is anchored to absolute time, so the
emitted audio does not inherit the pacing loop's scheduling jitter.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Any

import numpy as np

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
    model: str = ""  # reference mode: the agent's language model

    @classmethod
    def from_query(cls, query: dict[str, str]) -> FixtureConfig:
        cfg = cls()
        types = {f.name: f.type for f in fields(cls)}
        for k, v in query.items():
            if k not in types:
                continue
            if k == "mode":
                if v not in ("calibration", "agent", "echo", "reference", "silent"):
                    raise ValueError(f"unknown fixture mode {v!r}")
                cfg.mode = v
            elif k == "greeting":
                cfg.greeting = v.lower() in ("1", "true", "yes")
            elif k == "voice":
                cfg.voice = v[:64]
            elif k == "model":
                cfg.model = "".join(ch for ch in v if ch.isalnum() or ch in "-._/")[:64]
            elif k == "yield_ms":
                cfg.yield_ms = None if v.lower() in ("", "none", "never") else float(v)
            else:
                setattr(cfg, k, float(v))
        cfg.delay_ms = min(max(cfg.delay_ms, 0.0), 10_000.0)
        cfg.endpoint_ms = min(max(cfg.endpoint_ms, 60.0), 3000.0)
        cfg.response_ms = min(max(cfg.response_ms, 20.0), 30_000.0)
        return cfg


@lru_cache(maxsize=256)
def _speech(line: str, voice: str, rate: float) -> np.ndarray:
    """Scripted agent speech, cached: the lines repeat across calls. espeak when installed, else babble."""
    from gauntlet.caller.local_synth import synthesize_local

    pcm = synthesize_local(line, voice, rate)[0]
    pcm.setflags(write=False)
    return pcm


def _first_audible(pcm: np.ndarray, amplitude: int = 32) -> int:
    """Index of the first sample above about -60 dBFS: where a listener's detector can start to hear it."""
    hits = np.nonzero(np.abs(pcm.astype(np.int32)) > amplitude)[0]
    return int(hits[0]) if hits.size else 0


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
        self._pending: tuple[int, str, np.ndarray | None] | None = None  # (start_ns, label, audio) not yet rendered
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
        # reference mode: a real STT -> LLM -> TTS pipeline (falls back to scripted lines without a key)
        self._pipeline: Any = None
        if cfg.mode == "reference":
            from fixtures.reference_agent.pipeline import ReferencePipeline

            p = ReferencePipeline(llm_model=cfg.model or None, rate=cfg.rate)
            self._pipeline = p if p.cfg.available else None
        self._preroll: deque[np.ndarray] = deque(maxlen=12)
        self._utt: list[np.ndarray] = []
        self._collecting = False
        self._task: asyncio.Task[None] | None = None  # the reply being prepared; a caller who keeps talking cancels it
        self._greeting_task: asyncio.Task[None] | None = None  # never cancelled by caller audio
        self._gen = 0  # bumps on every schedule or cancel, so a late-finishing synthesis never plays

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
            if self.cfg.greeting and self.cfg.mode in ("agent", "reference"):
                if self._pipeline is not None:
                    from fixtures.reference_agent.pipeline import GREETING

                    self._greeting_task = asyncio.get_running_loop().create_task(self._speak_greeting(GREETING))
                else:
                    self._schedule(now_ns() + 300 * 1_000_000, "greeting")
        elif msg.get("type") == "bye":
            self._stop.set()
            return False
        return True

    def on_frame(self, data: bytes, t_recv_ns: int) -> None:
        if len(data) != FRAME_SAMPLES * 2:
            return
        frame = from_bytes(data)
        if self.cfg.mode == "silent":  # connects, receives, never speaks (TC-014)
            return
        if self.cfg.mode == "calibration":
            self._on_calibration_frame(frame, t_recv_ns)
        elif self._pipeline is not None:
            self._on_reference_frame(frame, t_recv_ns)
        else:
            self._on_agent_frame(frame, t_recv_ns)

    def stop(self) -> None:
        self._stop.set()
        for task in (self._task, self._greeting_task):
            if task is not None:
                task.cancel()
        if self._pipeline is not None:
            asyncio.get_running_loop().create_task(self._pipeline.aclose())

    # -- reference pipeline -----------------------------------------------------------------------
    def _on_reference_frame(self, frame: np.ndarray, t: int) -> None:
        evs = self._probe.process(frame, t)
        (self._utt if self._collecting else self._preroll).append(frame.copy())
        for ev in evs:
            if ev.kind == "speech_onset":
                self._barge_in(ev.t_ns)
                if self._task is not None and not self._task.done():
                    self._task.cancel()  # the caller kept talking: answer the whole thing later
                if not self._collecting:
                    self._utt.extend(self._preroll)
                    self._preroll.clear()
                    self._collecting = True
            else:
                self._collecting = False
                pcm = np.concatenate(self._utt) if self._utt else np.zeros(0, dtype=np.int16)
                self._task = asyncio.get_running_loop().create_task(self._respond(pcm, ev.t_ns))

    async def _respond(self, pcm: np.ndarray, t_offset: int) -> None:
        try:
            heard, said, audio = await self._pipeline.turn(pcm)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            heard, said, audio = None, "Sorry, I didn't catch that.", None
            self._markers.append({"type": "marker", "kind": "pipeline_error", "error": type(e).__name__})
        if said is None:  # no words in what was heard: no reply
            self._utt = []
            return
        # what the agent heard and will say: shown by the browser "talk to the agent" page, ignored by the rig
        self._markers.append({"type": "marker", "kind": "transcript", "heard": heard, "said": said,
                              "timings": self._pipeline.last_timings})
        self._utt = []
        if audio is None:
            audio = await asyncio.to_thread(_speech, said, self.cfg.voice, self.cfg.rate)
        # speak as soon as the pipeline is ready; delay_ms is a floor (a configurable minimum think time)
        start = max(now_ns(), t_offset + int(self.cfg.delay_ms * 1_000_000))
        self._pending = (start, "reply", audio)
        self._markers.append({"type": "marker", "kind": "trigger", "label": "reply", "t_ns": t_offset,
                              "scheduled_ns": start, "timings": self._pipeline.last_timings})

    async def _speak_greeting(self, text: str) -> None:
        audio = await self._pipeline.speak(text)
        self._pipeline.history.append({"role": "assistant", "content": text})
        self._markers.append({"type": "marker", "kind": "transcript", "heard": None, "said": text, "timings": {}})
        self._pending = (now_ns() + 200 * 1_000_000, "greeting", audio)

    # -- input ------------------------------------------------------------------------------------
    def _barge_in(self, onset_ns: int) -> None:
        tr = self._track
        if tr is None or tr.stop_ns is not None:
            # the reference agent speaks its greeting whatever the line sounds like, so room noise on a browser
            # microphone cannot drop it; the scripted agent keeps its behaviour so committed benchmarks replay
            keep = self._pipeline is not None and self._pending is not None and self._pending[1] == "greeting"
            if self._pending is not None and self._pending[0] > onset_ns and not keep:
                self._pending = None  # caller resumed before we committed: wait for them
                self._gen += 1
            elif self._pending is None:
                self._gen += 1  # a reply still being synthesised is superseded too
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
        self._gen += 1
        if label in ("greeting", "reply") and self.cfg.mode != "calibration":
            # Speech is synthesised off the event loop and ahead of its start time. Synthesising inside
            # the render loop stalls every call sharing the process — the rig benchmark caught it.
            line = self._next_line(label)
            self._pending = None
            asyncio.get_running_loop().create_task(self._prepare(start_ns, label, line, self._gen))
        else:
            self._pending = (start_ns, label, None)
        if trigger_ns is not None:
            self._markers.append({"type": "marker", "kind": "trigger", "label": label, "t_ns": trigger_ns,
                                  "scheduled_ns": start_ns})

    async def _prepare(self, start_ns: int, label: str, line: str, gen: int) -> None:
        audio = await asyncio.to_thread(_speech, line, self.cfg.voice, self.cfg.rate)
        if gen == self._gen:  # not superseded or cancelled by the caller resuming
            self._pending = (start_ns, label, audio)

    def _next_line(self, label: str) -> str:
        if label == "greeting":
            self._turn = 1
            return AGENT_SCRIPT[0]
        idx = max(1, self._turn)
        self._turn = idx + 1
        return AGENT_SCRIPT[min(idx, len(AGENT_SCRIPT) - 1)]

    def _response_pcm(self, label: str) -> np.ndarray:
        c = self.cfg
        if c.mode == "calibration":
            return tone(c.tone_hz, c.response_ms, c.level_db)
        if label == "echo":
            return self._echo_last if self._echo_last is not None else tone(440, 300, -20)
        return _speech(self._next_line(label), c.voice, c.rate)

    # -- output -----------------------------------------------------------------------------------
    def _render(self, now: int, frame_ns: int | None = None) -> np.ndarray:
        """One output frame. Samples are indexed by the frame's nominal time (``frame_ns``, advancing exactly
        20 ms per frame) so consecutive frames are contiguous: indexing by the wall clock skipped or repeated
        samples whenever the pacing loop woke a little late, which sounded like a torn speaker. Markers still
        report ``now``, the instant the frame actually leaves, which is the calibration ground truth."""
        ref = now if frame_ns is None else frame_ns
        late = now - ref
        if self._pending is not None and self._pending[0] < ref + FRAME_NS:
            start, label, audio = self._pending
            self._pending = None
            self._track = _Track(audio if audio is not None else self._response_pcm(label), start, label)
        tr = self._track
        out = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        if tr is None:
            return out
        start_idx = int(round((ref - tr.start_ns) / SAMPLE_NS))
        stop_idx = len(tr.pcm)
        if tr.stop_ns is not None:
            stop_idx = min(stop_idx, max(0, int(round((tr.stop_ns - tr.start_ns) / SAMPLE_NS))))
        a, b = max(start_idx, 0), min(start_idx + FRAME_SAMPLES, stop_idx)
        if b > a:
            out[a - start_idx : b - start_idx] = tr.pcm[a:b]
            if not tr.started_reported:
                tr.started_reported = True
                tr.actual_start_ns = ref + late + int(round((a - start_idx) * SAMPLE_NS))
                audible = _first_audible(tr.pcm)
                self._markers.append({"type": "marker", "kind": "response_start", "label": tr.label,
                                      "t_ns": tr.actual_start_ns, "scheduled_ns": tr.start_ns,
                                      "late_ns": tr.actual_start_ns - tr.start_ns,
                                      # when the first audible sample leaves (leading silence excluded)
                                      "t_voiced_ns": tr.actual_start_ns + int(round(max(0, audible - a) * SAMPLE_NS))})
        if start_idx + FRAME_SAMPLES >= stop_idx:
            end_ns = ref + late + int(round((stop_idx - start_idx) * SAMPLE_NS))
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
            frame = self._render(now, target)
            try:
                # markers first: a reply's transcript reaches the peer before the reply's first audio frame
                while self._markers:
                    await self._send_text(json.dumps(self._markers.pop(0)))
                await self._send_bytes(to_bytes(frame))
            except Exception:
                self._stop.set()
                return
            i += 1
