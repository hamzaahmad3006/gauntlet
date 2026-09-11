"""Inbound media: transport frames -> playout clock -> probe -> recorder, with async waits on speech events.

The receive path is the measurement tap. It sits on the raw received stream, before anything else can
touch it (SRS 47.1: an inbound impairment stage, if ever built, must go after this tap).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import numpy as np

from gauntlet.media.audio import dbfs
from gauntlet.media.probe import PlayoutClock, Probe, ProbeConfig, SpeechEvent
from gauntlet.media.recorder import CallRecorder

ONSET_CONFIRM_SLACK_S = 0.12  # 3 confirmation frames plus scheduling slack
OFFSET_CONFIRM_SLACK_S = 0.40  # 15 hangover frames plus slack


class ReceivePath:
    def __init__(self, probe_config: ProbeConfig | None = None, recorder: CallRecorder | None = None,
                 on_event: Callable[[SpeechEvent], None] | None = None,
                 on_frame: Callable[[np.ndarray, int], None] | None = None):
        self.probe = Probe(probe_config or ProbeConfig())
        self.playout = PlayoutClock()
        self.recorder = recorder
        self.on_event = on_event
        self.on_frame = on_frame
        self.intervals: list[tuple[int, int]] = []  # closed agent speech intervals
        self.open_onset: int | None = None
        self.events: list[SpeechEvent] = []
        self._pulse = asyncio.Event()
        self.frames = 0
        self.audio_frames_above_floor = 0
        self.last_t: int | None = None

    def feed(self, frame: np.ndarray, t_recv_ns: int) -> list[SpeechEvent]:
        level = dbfs(frame)
        quiet = level <= self.probe.threshold_db()
        t = self.playout.stamp(t_recv_ns, quiet)
        self.last_t = t
        self.frames += 1
        if not quiet:
            self.audio_frames_above_floor += 1
        if self.recorder is not None:
            self.recorder.write(1, frame, t)
        if self.on_frame is not None:
            self.on_frame(frame, t)
        evs = self.probe.process(frame, t, level)
        for ev in evs:
            self._apply(ev)
        return evs

    def _apply(self, ev: SpeechEvent) -> None:
        if ev.kind == "speech_onset":
            self.open_onset = ev.t_ns
        elif ev.kind == "speech_offset" and self.open_onset is not None:
            self.intervals.append((self.open_onset, ev.t_ns))
            self.open_onset = None
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)
        self._pulse.set()

    def finish(self) -> None:
        for ev in self.probe.flush():
            self._apply(ev)

    @property
    def speaking(self) -> bool:
        return self.open_onset is not None

    def all_intervals(self, end_ns: int | None = None) -> list[tuple[int, int]]:
        out = list(self.intervals)
        if self.open_onset is not None and end_ns is not None:
            out.append((self.open_onset, end_ns))
        return out

    async def _wait_for(self, predicate: Callable[[], SpeechEvent | None], timeout_s: float) -> SpeechEvent | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            hit = predicate()
            if hit is not None:
                return hit
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            self._pulse.clear()
            try:
                await asyncio.wait_for(self._pulse.wait(), remaining)
            except asyncio.TimeoutError:
                return predicate()

    async def wait_onset(self, after_ns: int, timeout_s: float) -> SpeechEvent | None:
        """First agent onset at or after ``after_ns`` — or the onset of speech already in progress."""
        def pred() -> SpeechEvent | None:
            for ev in self.events:
                if ev.kind == "speech_onset" and ev.t_ns >= after_ns:
                    return ev
            return None
        return await self._wait_for(pred, timeout_s + ONSET_CONFIRM_SLACK_S)

    def onset_in_progress(self, since_ns: int) -> SpeechEvent | None:
        """An onset before ``since_ns`` whose speech is still open (agent talking over the caller)."""
        if self.open_onset is not None:
            for ev in reversed(self.events):
                if ev.kind == "speech_onset" and ev.t_ns == self.open_onset:
                    return ev
        return None

    async def wait_offset(self, after_ns: int, timeout_s: float) -> SpeechEvent | None:
        def pred() -> SpeechEvent | None:
            for ev in self.events:
                if ev.kind == "speech_offset" and ev.t_ns >= after_ns:
                    return ev
            return None
        return await self._wait_for(pred, timeout_s + OFFSET_CONFIRM_SLACK_S)

    async def wait_silence(self, gap_ms: float, max_s: float) -> bool:
        """Wait until the agent has been silent for ``gap_ms`` — a human caller does not jump into the
        agent's sentence pauses. Returns False if the agent never went quiet within ``max_s``."""
        from gauntlet.common.clock import now_ns

        gap_ns = int(gap_ms * 1_000_000)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            if self.open_onset is None:
                last_end = self.intervals[-1][1] if self.intervals else 0
                quiet_for = now_ns() - last_end
                if quiet_for >= gap_ns:
                    return True
                wait = min(remaining, (gap_ns - quiet_for) / 1e9)
            else:
                wait = remaining
            self._pulse.clear()
            try:
                await asyncio.wait_for(self._pulse.wait(), wait)
            except asyncio.TimeoutError:
                pass

    async def wait_quiet(self, max_s: float) -> bool:
        """Wait until the agent is not speaking (no open onset), up to max_s."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_s
        while self.open_onset is not None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            self._pulse.clear()
            try:
                await asyncio.wait_for(self._pulse.wait(), remaining)
            except asyncio.TimeoutError:
                return self.open_onset is None
        return True
