"""Audio primitives. Internal format everywhere: 16 kHz mono signed 16-bit, 20 ms frames (SRS 12.2).

Timeline convention used by every measurement: a frame stamped ``t`` covers the samples playing over
``[t, t + 20 ms)``, so sample ``i`` of that frame is at ``t + i / 16000`` seconds.
"""

from __future__ import annotations

import math

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_BYTES = FRAME_SAMPLES * 2  # 640
FRAME_NS = FRAME_MS * 1_000_000
SAMPLE_NS = 1_000_000_000 / SAMPLE_RATE  # 62_500 ns
FULL_SCALE = 32768.0
SILENCE_DB = -120.0


def dbfs(samples: np.ndarray) -> float:
    """RMS level in dBFS relative to int16 full scale. Digital silence reports SILENCE_DB, not -inf."""
    if samples.size == 0:
        return SILENCE_DB
    x = samples.astype(np.float64)
    rms = math.sqrt(float(np.mean(x * x)))
    if rms <= 0.0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(rms / FULL_SCALE))


def db_to_amplitude(db: float) -> float:
    return FULL_SCALE * (10.0 ** (db / 20.0))


def to_int16(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x), -32768, 32767).astype(np.int16)


def silence(n_samples: int) -> np.ndarray:
    return np.zeros(n_samples, dtype=np.int16)


def silence_ms(ms: float) -> np.ndarray:
    return silence(int(round(ms * SAMPLE_RATE / 1000)))


def tone(freq_hz: float, duration_ms: float, level_dbfs: float = -12.0, sr: int = SAMPLE_RATE) -> np.ndarray:
    """A sine burst whose RMS equals ``level_dbfs``. No fades: calibration needs sharp edges."""
    n = int(round(duration_ms * sr / 1000))
    t = np.arange(n, dtype=np.float64) / sr
    peak = db_to_amplitude(level_dbfs) * math.sqrt(2.0)
    return to_int16(peak * np.sin(2.0 * math.pi * freq_hz * t))


def frames_of(pcm: np.ndarray) -> list[np.ndarray]:
    """Split into 20 ms frames, zero-padding the final frame."""
    n = len(pcm)
    if n == 0:
        return []
    count = (n + FRAME_SAMPLES - 1) // FRAME_SAMPLES
    padded = np.zeros(count * FRAME_SAMPLES, dtype=np.int16)
    padded[:n] = pcm
    return [padded[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES] for i in range(count)]


def to_bytes(frame: np.ndarray) -> bytes:
    return frame.astype("<i2", copy=False).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.int16)


def voiced_span(pcm: np.ndarray, rel_db: float = -35.0, abs_floor_db: float = -60.0) -> tuple[int, int] | None:
    """First and one-past-last sample of the voiced region, using 10 ms energy windows.

    Used to find where a synthesised utterance actually starts and ends, so that trailing silence in
    provider output is not mistaken for the caller still speaking. Returns None for silent input.
    """
    win = SAMPLE_RATE // 100
    if len(pcm) < win:
        return None
    n_win = len(pcm) // win
    x = pcm[: n_win * win].astype(np.float64).reshape(n_win, win)
    rms = np.sqrt(np.mean(x * x, axis=1))
    with np.errstate(divide="ignore"):
        levels = 20.0 * np.log10(np.maximum(rms, 1e-9) / FULL_SCALE)
    peak = float(levels.max())
    thr = max(peak + rel_db, abs_floor_db)
    idx = np.nonzero(levels > thr)[0]
    if idx.size == 0:
        return None
    return int(idx[0] * win), int(min(len(pcm), (idx[-1] + 1) * win))


def raised_cosine(n: int) -> np.ndarray:
    """Rising half-cosine window of length n, 0 -> 1."""
    if n <= 0:
        return np.zeros(0)
    return 0.5 - 0.5 * np.cos(np.pi * (np.arange(n) + 0.5) / n)


def resample_linear(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resampler. Adequate for 48 kHz <-> 16 kHz speech-band audio in the media
    path; not used on any timing-critical sample index (resampling preserves time, not samples)."""
    if src_rate == dst_rate or len(pcm) == 0:
        return pcm.astype(np.int16, copy=False)
    n_out = int(round(len(pcm) * dst_rate / src_rate))
    x_old = np.arange(len(pcm), dtype=np.float64)
    x_new = np.linspace(0, len(pcm) - 1, n_out)
    return to_int16(np.interp(x_new, x_old, pcm.astype(np.float64)))


def time_stretch(pcm: np.ndarray, rate: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Overlap-add time stretch preserving pitch approximately (SRS-FR-055 local fallback).

    ``rate`` > 1 speaks faster (shorter output). Hann-windowed OLA, 40 ms grains, 50% output overlap.
    Crude but deterministic, and duration changes are exact, which is what the metric needs.
    """
    if abs(rate - 1.0) < 1e-3 or len(pcm) == 0:
        return pcm
    grain = int(0.040 * sr)
    hop_out = grain // 2
    hop_in = hop_out * rate
    x = pcm.astype(np.float64)
    n_grains = max(1, int((len(x) - grain) / hop_in) + 1)
    out = np.zeros(n_grains * hop_out + grain)
    norm = np.zeros_like(out)
    window = np.hanning(grain)
    for g in range(n_grains):
        s = int(round(g * hop_in))
        seg = x[s : s + grain]
        if len(seg) < grain:
            seg = np.pad(seg, (0, grain - len(seg)))
        o = g * hop_out
        out[o : o + grain] += seg * window
        norm[o : o + grain] += window
    out = out / np.maximum(norm, 1e-6)
    target = int(round(len(x) / rate))
    return to_int16(out[:target])
