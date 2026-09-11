"""ARC-022 acoustic probe — energy VAD with an adaptive floor on the received stream (SRS-FR-060, 17.3–17.4).

Per 20 ms frame: RMS in dBFS. The noise floor is the 10th percentile of the most recent 150
non-speech frames (3 s). Speech threshold = floor + SPEECH_MARGIN_DB (12). Onset is confirmed after 3
consecutive frames above threshold and reported at the *first* of them; offset is confirmed after 15
consecutive frames below and reported at the end of the last above-threshold frame. The confirmation
and hangover windows are therefore removed from reported times instead of left as a bias.

Sub-frame interpolation: the onset time is the first sample in the confirming frame whose magnitude
exceeds the threshold amplitude; the offset time is one sample past the last such sample. This
reduces quantisation from ±10 ms to about ±1 ms; the accuracy claim itself comes from calibration.

Only below-threshold frames feed the floor estimate, so sustained speech cannot drag the floor up and
end itself. If no floor can be established within 2 s because the channel is continuously loud, the
probe falls back to a fixed −45 dBFS threshold and flags ``floor_fallback`` (SRS 17.6).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from gauntlet.media.audio import FRAME_NS, SAMPLE_NS, db_to_amplitude, dbfs


@dataclass(frozen=True, slots=True)
class SpeechEvent:
    kind: str  # "speech_onset" | "speech_offset"
    t_ns: int
    level_db: float
    truncated: bool = False  # offset synthesised at end of stream


@dataclass(slots=True)
class ProbeConfig:
    margin_db: float = 12.0
    onset_frames: int = 3
    offset_frames: int = 15
    floor_window: int = 150
    floor_percentile: float = 10.0
    min_floor_db: float = -75.0
    fallback_threshold_db: float = -45.0
    establish_frames: int = 10
    floor_timeout_frames: int = 100


@dataclass
class Probe:
    config: ProbeConfig = field(default_factory=ProbeConfig)

    def __post_init__(self) -> None:
        self._ring: deque[float] = deque(maxlen=self.config.floor_window)
        self._frames_seen = 0
        self._fallback = False
        self._in_speech = False
        self._pending: list[tuple[int, np.ndarray, float, float]] = []
        self._below = 0
        self._last_above: tuple[int, np.ndarray, float, float] | None = None
        self._peak_db = -120.0
        self.flags: set[str] = set()
        self.events: list[SpeechEvent] = []

    @property
    def speaking(self) -> bool:
        return self._in_speech

    def threshold_db(self) -> float:
        c = self.config
        if self._fallback:
            return c.fallback_threshold_db
        if len(self._ring) < c.establish_frames:
            if self._frames_seen >= c.floor_timeout_frames:
                self._fallback = True
                self.flags.add("floor_fallback")
            return c.fallback_threshold_db
        floor = max(float(np.percentile(np.fromiter(self._ring, float), c.floor_percentile)), c.min_floor_db)
        return floor + c.margin_db

    def is_quiet(self, frame: np.ndarray, level_db: float | None = None) -> bool:
        return (dbfs(frame) if level_db is None else level_db) <= self.threshold_db()

    def process(self, frame: np.ndarray, t_ns: int, level_db: float | None = None) -> list[SpeechEvent]:
        c = self.config
        self._frames_seen += 1
        db = dbfs(frame) if level_db is None else level_db
        thr = self.threshold_db()
        above = db > thr
        out: list[SpeechEvent] = []

        if not self._in_speech:
            if above:
                self._pending.append((t_ns, frame, thr, db))
                if len(self._pending) >= c.onset_frames:
                    t0, f0, thr0, _ = self._pending[0]
                    k = _first_sample_above(f0, thr0)
                    level = max(p[3] for p in self._pending)
                    out.append(SpeechEvent("speech_onset", t0 + int(round(k * SAMPLE_NS)), level))
                    self._in_speech = True
                    self._last_above = self._pending[-1]
                    self._peak_db = level
                    self._below = 0
                    self._pending.clear()
            else:
                self._pending.clear()
                self._ring.append(db)
        else:
            if above:
                self._below = 0
                self._last_above = (t_ns, frame, thr, db)
                self._peak_db = max(self._peak_db, db)
            else:
                self._below += 1
                self._ring.append(db)
                if self._below >= c.offset_frames:
                    out.append(self._offset_event(truncated=False))
                    self._in_speech = False
                    self._below = 0

        self.events.extend(out)
        return out

    def flush(self) -> list[SpeechEvent]:
        """Close speech still open at end of stream so every onset has an offset."""
        if not self._in_speech or self._last_above is None:
            return []
        ev = self._offset_event(truncated=True)
        self._in_speech = False
        self.events.append(ev)
        return [ev]

    def _offset_event(self, truncated: bool) -> SpeechEvent:
        assert self._last_above is not None
        t_la, f_la, thr_la, _ = self._last_above
        k = _last_sample_above(f_la, thr_la)
        return SpeechEvent("speech_offset", t_la + int(round((k + 1) * SAMPLE_NS)), self._peak_db, truncated)


def _first_sample_above(frame: np.ndarray, thr_db: float) -> int:
    hits = np.nonzero(np.abs(frame.astype(np.int32)) > db_to_amplitude(thr_db))[0]
    return int(hits[0]) if hits.size else 0


def _last_sample_above(frame: np.ndarray, thr_db: float) -> int:
    hits = np.nonzero(np.abs(frame.astype(np.int32)) > db_to_amplitude(thr_db))[0]
    return int(hits[-1]) if hits.size else len(frame) - 1


class PlayoutClock:
    """Maps frame arrival times to the times the audio would actually be heard.

    A speech frame cannot play before the previous frame has finished (a minimal playout buffer),
    so a target that bursts audio faster than real time is measured as heard, not as delivered.
    Silent frames may be compressed 2x, which drains any accumulated lag between utterances the way a
    real receiver's jitter buffer shrinks during silence. Timestamps stay monotonic.
    """

    def __init__(self) -> None:
        self._last: int | None = None
        self.max_lag_ns = 0

    def stamp(self, t_recv_ns: int, quiet: bool) -> int:
        if self._last is None:
            t = t_recv_ns
        else:
            t = max(t_recv_ns, self._last + (FRAME_NS // 2 if quiet else FRAME_NS))
        self._last = t
        self.max_lag_ns = max(self.max_lag_ns, t - t_recv_ns)
        return t
