"""Two-channel call recorder (deviation D-02): channel 0 = transmitted caller audio, channel 1 = received
agent audio, both placed on the one shared clock so they are aligned by construction. Also produces a
compact waveform peak file for the dashboard (min/max per 10 ms bin per channel).
"""

from __future__ import annotations

import io
import json

import numpy as np
import soundfile as sf

from gauntlet.media.audio import SAMPLE_NS, SAMPLE_RATE

PEAK_BIN = SAMPLE_RATE // 100  # 10 ms


class CallRecorder:
    def __init__(self, t0_ns: int, max_seconds: int = 300):
        self.t0_ns = t0_ns
        self._cap = (max_seconds + 5) * SAMPLE_RATE
        self._buf = np.zeros((self._cap, 2), dtype=np.int16)
        self._end = 0

    def write(self, channel: int, frame: np.ndarray, t_ns: int) -> None:
        start = int(round((t_ns - self.t0_ns) / SAMPLE_NS))
        if start < 0:
            frame, start = frame[-start:], 0
        end = min(start + len(frame), self._cap)
        if end <= start:
            return
        self._buf[start:end, channel] = frame[: end - start]
        self._end = max(self._end, end)

    @property
    def duration_s(self) -> float:
        return self._end / SAMPLE_RATE

    def wav_bytes(self) -> bytes:
        out = io.BytesIO()
        sf.write(out, self._buf[: self._end], SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return out.getvalue()

    def channel(self, channel: int) -> np.ndarray:
        return self._buf[: self._end, channel].copy()

    def peaks(self) -> dict:
        n_bins = max(1, self._end // PEAK_BIN)
        data = self._buf[: n_bins * PEAK_BIN].astype(np.int32).reshape(n_bins, PEAK_BIN, 2)
        peaks = np.abs(data).max(axis=1) / 32768.0
        return {
            "bin_ms": 10,
            "caller": [round(float(v), 4) for v in peaks[:, 0]],
            "agent": [round(float(v), 4) for v in peaks[:, 1]],
        }

    def peaks_json(self) -> bytes:
        return json.dumps(self.peaks(), separators=(",", ":")).encode()
