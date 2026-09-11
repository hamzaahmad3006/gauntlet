"""ARC-024 chaos engine — deterministic impairment of the caller's outbound audio (SRS 15, FR-051..054).

Fixed stage order, applied to every outbound 20 ms frame (SRS 15.1):

    noise mix -> jitter -> frame substitution -> fixed delay -> transmit

Content stages (noise, substitution) change samples; timing stages (jitter, delay) change the frame's
release time. Each stage draws from its own seeded stream (``chaos.noise``, ``chaos.jitter``,
``chaos.loss``), so enabling one stage never shifts another stage's schedule.

Honesty notes, repeated in docs/LIMITATIONS.md:
- frame substitution (D-05) is pre-encode replacement with silence or a faded repeat. It approximates
  packet loss; it does not reproduce receiver-side concealment artefacts;
- jitter is transmit-side release-time variation, not network variance meeting an adaptive buffer;
- nothing is applied to the agent-to-caller direction.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from typing import Any

import numpy as np

from gauntlet.common import seeds
from gauntlet.media.audio import FRAME_MS, FRAME_NS, FRAME_SAMPLES, raised_cosine, to_int16
from gauntlet.media.noise import NOISE_BEDS, noise_bed

FADE_SAMPLES = 32  # 2 ms at 16 kHz
NOMINAL_SPEECH_RMS = 32768.0 * 10 ** (-24 / 20)  # used for noise gain before the first utterance

# SRS 15.2 safety limits
LIMITS = {
    "loss_probability": (0.0, 0.20),
    "burst_length": (1.0, 10.0),
    "jitter_mean_ms": (0.0, 500.0),
    "jitter_stddev_ms": (0.0, 250.0),
    "jitter_max_ms": (0.0, 500.0),
    "jitter_depth": (1, 25),
    "delay_ms": (0.0, 2000.0),
    "snr_db": (5.0, 30.0),
    "interruptions_per_call": (0, 5),
    "pause_ms": (0.0, 3000.0),
    "speech_rate": (0.7, 1.3),
}


class ConditionError(ValueError):
    def __init__(self, parameter: str, value: Any, permitted: tuple[Any, Any]):
        super().__init__(f"{parameter}={value} outside permitted range {permitted[0]}..{permitted[1]}")
        self.parameter = parameter
        self.permitted = permitted


@dataclass(frozen=True, slots=True)
class ChaosParams:
    # CH-02 frame loss
    loss_probability: float = 0.0
    burst_length: float = 1.0
    concealment: str = "silence"
    # CH-03 jitter
    jitter_mean_ms: float = 0.0
    jitter_stddev_ms: float = 0.0
    jitter_max_ms: float = 0.0
    jitter_depth: int = 25
    # CH-04 added one-way delay
    delay_ms: float = 0.0
    # CH-05 noise
    noise_bed: str | None = None
    snr_db: float | None = None
    # CH-06 interruption and CH-07 slow caller are caller behaviour; carried here so one profile
    # object describes the whole condition, but applied by the caller, not by this pipeline.
    interruptions_per_call: int = 0
    offset_range_ms: tuple[float, float] = (400.0, 1500.0)
    pause_ms: float = 0.0
    speech_rate: float = 1.0

    @classmethod
    def from_profile(cls, parameters: dict[str, Any] | None, strict: bool = True) -> ChaosParams:
        """Parse the nested condition-profile document (suites/conditions.yaml)."""
        p = parameters or {}
        fl, ji, de = p.get("frame_loss") or {}, p.get("jitter") or {}, p.get("delay") or {}
        no, it, sc = p.get("noise") or {}, p.get("interruption") or {}, p.get("slow_caller") or {}
        rng_ms = it.get("offset_range_ms", [400, 1500])
        params = cls(
            loss_probability=float(fl.get("loss_probability", 0.0)),
            burst_length=float(fl.get("burst_length", 1.0)),
            concealment=str(fl.get("concealment", "silence")),
            jitter_mean_ms=float(ji.get("mean_ms", 0.0)),
            jitter_stddev_ms=float(ji.get("stddev_ms", 0.0)),
            jitter_max_ms=float(ji.get("max_ms", max(0.0, float(ji.get("mean_ms", 0.0)) * 3))),
            jitter_depth=int(ji.get("depth", 25)),
            delay_ms=float(de.get("delay_ms", 0.0)),
            noise_bed=no.get("noise_bed"),
            snr_db=float(no["snr_db"]) if "snr_db" in no else None,
            interruptions_per_call=int(it.get("interruptions_per_call", 0)),
            offset_range_ms=(float(rng_ms[0]), float(rng_ms[1])),
            pause_ms=float(sc.get("pause_ms", 0.0)),
            speech_rate=float(sc.get("speech_rate", 1.0)),
        )
        return params.validated() if strict else params.clamped()[0]

    def to_profile(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.loss_probability > 0:
            out["frame_loss"] = {"loss_probability": self.loss_probability, "burst_length": self.burst_length,
                                 "concealment": self.concealment}
        if self.jitter_mean_ms > 0 or self.jitter_stddev_ms > 0:
            out["jitter"] = {"mean_ms": self.jitter_mean_ms, "stddev_ms": self.jitter_stddev_ms,
                             "max_ms": self.jitter_max_ms, "depth": self.jitter_depth}
        if self.delay_ms > 0:
            out["delay"] = {"delay_ms": self.delay_ms}
        if self.noise_bed:
            out["noise"] = {"noise_bed": self.noise_bed, "snr_db": self.snr_db}
        if self.interruptions_per_call > 0:
            out["interruption"] = {"interruptions_per_call": self.interruptions_per_call,
                                   "offset_range_ms": list(self.offset_range_ms)}
        if self.pause_ms > 0 or self.speech_rate != 1.0:
            out["slow_caller"] = {"pause_ms": self.pause_ms, "speech_rate": self.speech_rate}
        return out

    def _checks(self) -> list[tuple[str, Any]]:
        checks: list[tuple[str, Any]] = [
            ("loss_probability", self.loss_probability), ("burst_length", self.burst_length),
            ("jitter_mean_ms", self.jitter_mean_ms), ("jitter_stddev_ms", self.jitter_stddev_ms),
            ("jitter_max_ms", self.jitter_max_ms), ("jitter_depth", self.jitter_depth),
            ("delay_ms", self.delay_ms), ("interruptions_per_call", self.interruptions_per_call),
            ("pause_ms", self.pause_ms), ("speech_rate", self.speech_rate),
        ]
        if self.snr_db is not None:
            checks.append(("snr_db", self.snr_db))
        return checks

    def validated(self) -> ChaosParams:
        for name, value in self._checks():
            lo, hi = LIMITS[name]
            if not lo <= value <= hi:
                raise ConditionError(name, value, (lo, hi))
        if self.concealment not in ("silence", "repeat"):
            raise ConditionError("concealment", self.concealment, ("silence", "repeat"))
        if self.noise_bed is not None and self.noise_bed not in NOISE_BEDS:
            raise ConditionError("noise_bed", self.noise_bed, NOISE_BEDS)
        lo, hi = self.offset_range_ms
        if not (200 <= lo <= hi <= 4000):
            raise ConditionError("offset_range_ms", self.offset_range_ms, (200, 4000))
        # overflow of the reorder buffer is made impossible by construction (SRS-FR-052)
        if self.jitter_max_ms > self.jitter_depth * FRAME_MS:
            raise ConditionError("jitter_max_ms", self.jitter_max_ms, (0, self.jitter_depth * FRAME_MS))
        return self

    def clamped(self) -> tuple[ChaosParams, list[str]]:
        """Clamp to safety limits (SRS 15.7: clamped at load and again at injection)."""
        changes: dict[str, Any] = {}
        for name, value in self._checks():
            lo, hi = LIMITS[name]
            if value < lo or value > hi:
                changes[name] = type(value)(min(max(value, lo), hi))
        p = replace(self, **changes)
        if p.jitter_max_ms > p.jitter_depth * FRAME_MS:
            changes["jitter_max_ms"] = float(p.jitter_depth * FRAME_MS)
            p = replace(p, jitter_max_ms=changes["jitter_max_ms"])
        return p, sorted(changes)

    @property
    def active(self) -> bool:
        return (self.loss_probability > 0 or self.jitter_mean_ms > 0 or self.jitter_stddev_ms > 0
                or self.delay_ms > 0 or self.noise_bed is not None)


@dataclass
class ChaosStats:
    frames_sent: int = 0
    frames_substituted: int = 0
    jitter_samples: int = 0
    jitter_sum_ms: float = 0.0
    jitter_sumsq_ms: float = 0.0
    jitter_max_ms: float = 0.0
    delay_ms: float = 0.0
    speech_energy: float = 0.0
    noise_energy: float = 0.0
    epochs: list[dict[str, Any]] = field(default_factory=list)

    def achieved(self, configured: ChaosParams) -> dict[str, Any]:
        out: dict[str, Any] = {"frames_sent": self.frames_sent, "frames_substituted": self.frames_substituted}
        if self.frames_sent:
            rate = self.frames_substituted / self.frames_sent
            out["achieved_loss_rate"] = round(rate, 6)
            out["configured_loss_rate"] = configured.loss_probability
            out["impairment_deviation"] = (
                configured.loss_probability > 0 and abs(rate - configured.loss_probability) > 0.01
            )
        if self.jitter_samples:
            mean = self.jitter_sum_ms / self.jitter_samples
            var = max(0.0, self.jitter_sumsq_ms / self.jitter_samples - mean * mean)
            out["achieved_jitter_mean_ms"] = round(mean, 3)
            out["achieved_jitter_stddev_ms"] = round(math.sqrt(var), 3)
            out["achieved_jitter_max_ms"] = round(self.jitter_max_ms, 3)
        out["injected_delay_ms"] = self.delay_ms
        if self.noise_energy > 0 and self.speech_energy > 0:
            out["achieved_snr_db"] = round(10 * math.log10(self.speech_energy / self.noise_energy), 3)
            out["configured_snr_db"] = configured.snr_db
        out["epochs"] = self.epochs
        return out


class ChaosPipeline:
    """Stateful per-call impairment. Not thread-safe; owned by one transmitter."""

    def __init__(self, params: ChaosParams, call_seed: int):
        self.params = params
        self.stats = ChaosStats(delay_ms=params.delay_ms)
        self._rng_loss = seeds.rng(call_seed, "chaos.loss")
        self._rng_jitter = seeds.rng(call_seed, "chaos.jitter")
        self._rng_noise = seeds.rng(call_seed, "chaos.noise")
        self._bad = False
        self._next_lost = self._draw_loss()
        self._prev_lost = False
        self._prev_frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        self._consecutive_lost = 0
        self._noise: np.ndarray | None = None
        self._noise_pos = 0
        self._noise_gain = 0.0
        self._set_noise(params)
        self.stats.epochs.append({"epoch": 0, "parameters": params.to_profile()})

    # -- configuration ---------------------------------------------------------------------------
    def set_params(self, params: ChaosParams, epoch: int) -> None:
        """Adopt new parameters (SRS-FR-038). Callers apply this at a turn boundary only."""
        self.params = params
        self.stats.delay_ms = params.delay_ms
        self._set_noise(params)
        self.stats.epochs.append({"epoch": epoch, "parameters": params.to_profile()})

    def _set_noise(self, params: ChaosParams) -> None:
        if params.noise_bed and params.snr_db is not None:
            if self._noise is None:
                self._noise = noise_bed(params.noise_bed)
                self._noise_pos = int(self._rng_noise.integers(0, len(self._noise)))
            self._noise_gain = self._gain_for(NOMINAL_SPEECH_RMS)
        else:
            self._noise = None
            self._noise_gain = 0.0

    def _gain_for(self, speech_rms: float) -> float:
        if self._noise is None or self.params.snr_db is None:
            return 0.0
        bed_rms = float(np.sqrt(np.mean(self._noise.astype(np.float64) ** 2)))
        return speech_rms / (bed_rms * 10 ** (self.params.snr_db / 20.0))

    def begin_utterance(self, voiced_pcm: np.ndarray) -> None:
        """Set the noise gain from this utterance's voiced RMS (SRS-FR-053)."""
        if self._noise is not None and len(voiced_pcm):
            rms = float(np.sqrt(np.mean(voiced_pcm.astype(np.float64) ** 2)))
            if rms > 0:
                self._noise_gain = self._gain_for(rms)

    # -- per frame --------------------------------------------------------------------------------
    def _draw_loss(self) -> bool:
        p = self.params.loss_probability
        if p <= 0:
            self._bad = False
            return False
        r = 1.0 / max(1.0, self.params.burst_length)
        q = p * r / (1.0 - p)
        u = float(self._rng_loss.random())
        self._bad = (u >= r) if self._bad else (u < q)
        return self._bad

    def _draw_jitter_ms(self) -> float:
        p = self.params
        if p.jitter_mean_ms <= 0 and p.jitter_stddev_ms <= 0:
            return 0.0
        for _ in range(16):  # truncated normal by bounded rejection, deterministic either way
            x = float(self._rng_jitter.normal(p.jitter_mean_ms, p.jitter_stddev_ms))
            if 0.0 <= x <= p.jitter_max_ms:
                return x
        return min(max(x, 0.0), p.jitter_max_ms)

    def process(self, frame: np.ndarray, nominal_ns: int, voiced: bool) -> tuple[np.ndarray, int, bool]:
        """Returns (frame to transmit, release time in ns, substituted?)."""
        out = frame
        # 1. noise mix (continuous: a room is noisy whether or not the caller is speaking)
        if self._noise is not None and self._noise_gain > 0:
            n = len(self._noise)
            idx = (self._noise_pos + np.arange(FRAME_SAMPLES)) % n
            self._noise_pos = (self._noise_pos + FRAME_SAMPLES) % n
            noise = self._noise[idx].astype(np.float64) * self._noise_gain
            if voiced:
                self.stats.speech_energy += float(np.sum(frame.astype(np.float64) ** 2))
                self.stats.noise_energy += float(np.sum(noise**2))
            out = to_int16(frame.astype(np.float64) + noise)
        # 2. jitter (release-time variation)
        jitter_ms = self._draw_jitter_ms()
        if jitter_ms or self.params.jitter_stddev_ms > 0:
            s = self.stats
            s.jitter_samples += 1
            s.jitter_sum_ms += jitter_ms
            s.jitter_sumsq_ms += jitter_ms * jitter_ms
            s.jitter_max_ms = max(s.jitter_max_ms, jitter_ms)
        # 3. frame substitution with one-step lookahead so fades know both neighbours
        lost = self._next_lost
        self._next_lost = self._draw_loss()
        if lost:
            out = self._conceal(out)
            self.stats.frames_substituted += 1
            self._consecutive_lost += 1
        else:
            self._consecutive_lost = 0
            self._prev_frame = out
        self._prev_lost = lost
        self.stats.frames_sent += 1
        # 4. fixed delay
        release = nominal_ns + int(round((jitter_ms + self.params.delay_ms) * 1_000_000))
        return out, release, lost

    def _conceal(self, original: np.ndarray) -> np.ndarray:
        fade = raised_cosine(FADE_SAMPLES)
        if self.params.concealment == "repeat":
            body = self._prev_frame.astype(np.float64) * (0.5 ** self._consecutive_lost)
        else:
            body = np.zeros(FRAME_SAMPLES)
        out = body.copy()
        orig = original.astype(np.float64)
        if not self._prev_lost:  # fade out of the audio the listener was hearing
            out[:FADE_SAMPLES] = orig[:FADE_SAMPLES] * fade[::-1] + body[:FADE_SAMPLES] * fade
        if not self._next_lost:  # fade back into the next delivered frame
            out[-FADE_SAMPLES:] = body[-FADE_SAMPLES:] * fade[::-1] + orig[-FADE_SAMPLES:] * fade
        return to_int16(out)


def describe(params: ChaosParams) -> dict[str, Any]:
    return asdict(params)


FRAME_PERIOD_NS = FRAME_NS
