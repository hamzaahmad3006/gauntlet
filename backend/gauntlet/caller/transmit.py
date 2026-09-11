"""Paced outbound media: utterances -> 20 ms frames -> chaos pipeline -> transport.

The transmitter produces one frame per 20 ms nominal tick (speech or silence — a microphone never stops),
passes it through the chaos pipeline, and releases it to the transport at the pipeline's release time.
It records the *actual* transmit time of every utterance frame, so the caller's speech intervals and its
last voiced sample are known on the shared clock after every impairment stage (measurement-integrity
timeline convention). Utterances can be scheduled to start at a sample-accurate instant, which is how
seeded interruptions fire at their exact offset after agent speech onset.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from gauntlet.caller.adapters.base import Transport
from gauntlet.common.clock import now_ns
from gauntlet.media.audio import FRAME_NS, FRAME_SAMPLES, SAMPLE_NS, frames_of, silence, voiced_span
from gauntlet.media.chaos import ChaosParams, ChaosPipeline
from gauntlet.media.recorder import CallRecorder

HIST_BIN_MS = 5
HIST_BINS = 41  # 0..200 ms, last bin = 200+


@dataclass(eq=False)
class Utterance:
    pcm: np.ndarray
    segments: list[tuple[int, int]]  # voiced spans, utterance sample indices [start, end)
    text: str = ""
    kind: str = "speech"  # speech | interruption | prompt | tone
    start_at_ns: int | None = None
    # filled by the transmitter
    lead: int = 0
    frames: list[np.ndarray] = field(default_factory=list)
    frame_sent: list[int | None] = field(default_factory=list)
    frame_nominal: list[int | None] = field(default_factory=list)
    produced: int = 0
    sent: int = 0
    truncated: bool = False
    done: asyncio.Event = field(default_factory=asyncio.Event)
    first_voiced_ns: int | None = None
    last_voiced_ns: int | None = None
    last_voiced_nominal_ns: int | None = None
    voiced_intervals: list[tuple[int, int]] = field(default_factory=list)

    @classmethod
    def from_pcm(cls, pcm: np.ndarray, text: str = "", kind: str = "speech",
                 segments: list[tuple[int, int]] | None = None, start_at_ns: int | None = None) -> Utterance:
        if segments is None:
            span = voiced_span(pcm)
            segments = [span] if span else []
        return cls(pcm=pcm, segments=segments, text=text, kind=kind, start_at_ns=start_at_ns)

    @property
    def duration_ms(self) -> float:
        return len(self.pcm) / 16.0

    def _time(self, j: int, which: list[int | None]) -> int | None:
        p = j + self.lead
        f = p // FRAME_SAMPLES
        if f >= len(which) or which[f] is None:
            return None
        return int(which[f] + round((p % FRAME_SAMPLES) * SAMPLE_NS))  # type: ignore[operator]

    def _finalise(self) -> None:
        produced_samples = self.produced * FRAME_SAMPLES - self.lead
        spans = []
        for s, e in self.segments:
            e = min(e, produced_samples)
            if e <= s:
                continue
            ts, te = self._time(s, self.frame_sent), self._time(e - 1, self.frame_sent)
            if ts is not None and te is not None:
                spans.append((ts, te + int(SAMPLE_NS)))
        self.voiced_intervals = spans
        if spans:
            self.first_voiced_ns = spans[0][0]
            self.last_voiced_ns = spans[-1][1]
            last_end = min(self.segments[-1][1], produced_samples)
            nominal = self._time(last_end - 1, self.frame_nominal)
            self.last_voiced_nominal_ns = nominal + int(SAMPLE_NS) if nominal is not None else None
        self.done.set()

    async def wait(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self.done.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


class Transmitter:
    def __init__(self, transport: Transport, chaos: ChaosPipeline, recorder: CallRecorder | None = None):
        self.transport = transport
        self.chaos = chaos
        self.recorder = recorder
        self._queue: deque[Utterance] = deque()
        self._current: Utterance | None = None
        self._stopped = asyncio.Event()
        self._wake = asyncio.Event()
        self._seq = itertools.count()
        self.voiced_intervals: list[tuple[int, int]] = []
        self.interval_hist = [0] * HIST_BINS
        self._last_sent: int | None = None
        self.frames_sent = 0
        self.lateness_max_ms = 0.0
        self.error: BaseException | None = None
        self._pending_params: tuple[ChaosParams, int] | None = None

    # -- control ---------------------------------------------------------------------------------
    def say(self, utt: Utterance) -> Utterance:
        self._queue.append(utt)
        self._wake.set()
        return utt

    @property
    def speaking(self) -> bool:
        return self._current is not None or bool(self._queue)

    def cancel_all(self) -> None:
        """Hang up mid-sentence: stop producing new utterance frames; frames in flight still finish."""
        while self._queue:
            u = self._queue.popleft()
            u.truncated = True
            self._complete(u)
        if self._current is not None:
            u = self._current
            u.frames = u.frames[: u.produced]
            u.truncated = True
            self._current = None
            if u.sent >= u.produced:
                self._complete(u)

    def _complete(self, u: Utterance) -> None:
        if not u.done.is_set():
            u._finalise()
            self.voiced_intervals.extend(u.voiced_intervals)

    def apply_params_at_next_utterance(self, params: ChaosParams, epoch: int) -> None:
        """Mid-run condition change (SRS-FR-038): adopted at the next utterance boundary, never mid-turn."""
        self._pending_params = (params, epoch)

    def stop(self) -> None:
        self._stopped.set()
        self._wake.set()

    # -- loop --------------------------------------------------------------------------------------
    def _begin(self, u: Utterance, nominal: int) -> None:
        if self._pending_params is not None:
            self.chaos.set_params(*self._pending_params)
            self._pending_params = None
        lead = 0
        if u.start_at_ns is not None:
            lead = int(min(max(round((u.start_at_ns - nominal) / SAMPLE_NS), 0), FRAME_SAMPLES - 1))
        u.lead = lead
        padded = np.concatenate([silence(lead), u.pcm]) if lead else u.pcm
        u.frames = frames_of(padded) or [silence(FRAME_SAMPLES)]
        u.frame_sent = [None] * len(u.frames)
        u.frame_nominal = [None] * len(u.frames)
        voiced = [u.pcm[s:e] for s, e in u.segments]
        self.chaos.begin_utterance(np.concatenate(voiced) if voiced else u.pcm[:0])
        self._current = u

    def _frame_voiced(self, u: Utterance, f: int) -> bool:
        a, b = f * FRAME_SAMPLES - u.lead, (f + 1) * FRAME_SAMPLES - u.lead
        return any(s < b and e > a for s, e in u.segments)

    def _next_frame(self, nominal: int) -> tuple[np.ndarray, Utterance | None, int, bool]:
        if self._current is None and self._queue:
            head = self._queue[0]
            if head.start_at_ns is None or head.start_at_ns < nominal + FRAME_NS:
                self._queue.popleft()
                self._begin(head, nominal)
        u = self._current
        if u is None:
            return silence(FRAME_SAMPLES), None, -1, False
        f = u.produced
        frame = u.frames[f]
        u.frame_nominal[f] = nominal
        u.produced += 1
        voiced = self._frame_voiced(u, f)
        if u.produced >= len(u.frames):
            self._current = None
        return frame, u, f, voiced

    async def run(self) -> None:
        heap: list[tuple[int, int, np.ndarray, Utterance | None, int]] = []
        t0 = now_ns() + FRAME_NS
        i = 0
        try:
            while not self._stopped.is_set():
                nominal = t0 + i * FRAME_NS
                now = now_ns()
                next_t = min(nominal, heap[0][0]) if heap else nominal
                if next_t > now:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), (next_t - now) / 1e9)
                    except asyncio.TimeoutError:
                        pass
                    continue
                if nominal <= now:
                    self.lateness_max_ms = max(self.lateness_max_ms, (now - nominal) / 1e6)
                    frame, u, f, voiced = self._next_frame(nominal)
                    out, release, _ = self.chaos.process(frame, nominal, voiced)
                    heapq.heappush(heap, (release, next(self._seq), out, u, f))
                    i += 1
                now = now_ns()
                while heap and heap[0][0] <= now:
                    _, _, out, u, f = heapq.heappop(heap)
                    await self.transport.send_frame(out)
                    t_sent = now_ns()
                    self._account(out, u, f, t_sent)
        except BaseException as e:  # surfaced to the session, which owns the reason code
            self.error = e
            raise

    def _account(self, out: np.ndarray, u: Utterance | None, f: int, t_sent: int) -> None:
        self.frames_sent += 1
        if self._last_sent is not None:
            gap_ms = (t_sent - self._last_sent) / 1e6
            self.interval_hist[min(int(gap_ms // HIST_BIN_MS), HIST_BINS - 1)] += 1
        self._last_sent = t_sent
        if self.recorder is not None:
            self.recorder.write(0, out, t_sent)
        if u is not None and f < len(u.frame_sent):
            u.frame_sent[f] = t_sent
            u.sent += 1
            if u.sent >= len(u.frames):
                self._complete(u)

    def achieved_intervals(self) -> dict:
        return {"bin_ms": HIST_BIN_MS, "counts": self.interval_hist, "frames_sent": self.frames_sent,
                "max_lateness_ms": round(self.lateness_max_ms, 3)}
