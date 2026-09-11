"""ARC-040 referee transcription — the agent's channel only, streamed to an independent recogniser
(SRS-FR-070, -071, deviation D-01).

Speaker attribution is structural: this client only ever hears the agent's received channel, and the
caller's words are known exactly because GAUNTLET synthesised them. Segment times from the recogniser
(seconds into the stream) are mapped back onto the shared clock through the playout time of the frame
that carried them. Exactly one referee engine may be enabled; substituting another engine mid-benchmark
is prohibited because it breaks cross-run comparability (SRS 28.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from gauntlet.media.audio import FRAME_MS, to_bytes


@dataclass
class Segment:
    t_start_ns: int
    t_end_ns: int
    text: str
    confidence: float | None


class AgentTranscriber:
    engine = "none"
    engine_version = ""

    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.audio_seconds = 0.0
        self.error: str | None = None
        self._t_by_frame: list[int] = []

    @property
    def enabled(self) -> bool:
        return False

    async def start(self) -> None:
        return None

    def feed(self, frame: np.ndarray, t_ns: int) -> None:
        return None

    async def settle(self, until_ns: int, timeout_s: float) -> None:
        """Wait (bounded) until finals covering audio up to ``until_ns`` have arrived."""
        return None

    def text_between(self, t0: int, t1: int) -> tuple[str | None, float | None]:
        hits = [s for s in self.segments if s.t_end_ns > t0 and s.t_start_ns < t1]
        if not hits:
            return (None, None) if not self.enabled else ("", None)
        confs = [s.confidence for s in hits if s.confidence is not None]
        return " ".join(s.text for s in hits).strip(), (sum(confs) / len(confs) if confs else None)

    async def close(self) -> None:
        return None


class NullTranscriber(AgentTranscriber):
    """No referee configured: no transcript, therefore no task-success scoring (SC-04 unavailable)."""


class SpeechmaticsTranscriber(AgentTranscriber):
    engine = "speechmatics-rt"
    engine_version = "v2"

    def __init__(self, api_key: str, url: str, language: str = "en", max_delay_s: float = 1.0):
        super().__init__()
        self.api_key = api_key
        self.url = url
        self.language = language
        self.max_delay_s = max_delay_s
        self._ws: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._buf: list[bytes] = []
        self._seq = 0
        self._covered_s = 0.0
        self._pulse = asyncio.Event()
        self._ended = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self.error is None

    async def start(self) -> None:
        import websockets

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(self.url, additional_headers={"Authorization": f"Bearer {self.api_key}"},
                                   max_size=2**22), 10)
            await self._ws.send(json.dumps({
                "message": "StartRecognition",
                "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": 16000},
                "transcription_config": {"language": self.language, "operating_point": "enhanced",
                                         "max_delay": self.max_delay_s, "enable_partials": False},
            }))
            while True:
                msg = json.loads(await asyncio.wait_for(self._ws.recv(), 10))
                if msg.get("message") == "RecognitionStarted":
                    break
                if msg.get("message") == "Error":
                    raise RuntimeError(f"{msg.get('type')}: {msg.get('reason')}")
            self._reader = asyncio.create_task(self._read())
        except Exception as e:
            self.error = f"referee_unavailable: {type(e).__name__}: {e}"[:300]

    def _frame_time(self, audio_s: float) -> int | None:
        if not self._t_by_frame:
            return None
        idx = int(audio_s * 1000 // FRAME_MS)
        idx = min(max(idx, 0), len(self._t_by_frame) - 1)
        rem_ns = int((audio_s * 1000 - idx * FRAME_MS) * 1_000_000)
        return self._t_by_frame[idx] + max(rem_ns, 0)

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                kind = msg.get("message")
                if kind == "AddTranscript":
                    words = [r for r in msg.get("results", []) if r.get("alternatives")]
                    if words:
                        text = ""
                        confs = []
                        for r in words:
                            alt = r["alternatives"][0]
                            tok = alt.get("content", "")
                            text += tok if r.get("type") == "punctuation" else (" " + tok)
                            if alt.get("confidence") is not None:
                                confs.append(float(alt["confidence"]))
                        s, e = float(words[0]["start_time"]), float(words[-1]["end_time"])
                        ts, te = self._frame_time(s), self._frame_time(e)
                        if ts is not None and te is not None:
                            self.segments.append(Segment(ts, te, text.strip(),
                                                         sum(confs) / len(confs) if confs else None))
                    end = (msg.get("metadata") or {}).get("end_time")
                    if end is not None:
                        self._covered_s = max(self._covered_s, float(end))
                    self._pulse.set()
                elif kind == "EndOfTranscript":
                    self._ended.set()
                    self._pulse.set()
                    return
                elif kind == "Error":
                    self.error = f"referee_error: {msg.get('type')}: {msg.get('reason')}"[:300]
                    self._pulse.set()
                    return
        except Exception as e:
            self.error = self.error or f"referee_stream_lost: {type(e).__name__}"
            self._pulse.set()

    def feed(self, frame: np.ndarray, t_ns: int) -> None:
        if self._ws is None or self.error:
            return
        self._t_by_frame.append(t_ns)
        self._buf.append(to_bytes(frame))
        self.audio_seconds += FRAME_MS / 1000
        if len(self._buf) >= 5:  # 100 ms chunks
            chunk, self._buf = b"".join(self._buf), []
            self._seq += 1
            asyncio.get_running_loop().create_task(self._send(chunk))

    async def _send(self, chunk: bytes) -> None:
        with contextlib.suppress(Exception):
            await self._ws.send(chunk)

    async def settle(self, until_ns: int, timeout_s: float) -> None:
        if self._ws is None or self.error:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            covered = self._frame_time(self._covered_s)
            if covered is not None and covered >= until_ns:
                return
            remaining = deadline - loop.time()
            if remaining <= 0 or self.error:
                return
            self._pulse.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._pulse.wait(), remaining)

    async def close(self) -> None:
        if self._ws is None:
            return
        with contextlib.suppress(Exception):
            if self._buf:
                await self._ws.send(b"".join(self._buf))
                self._seq += 1
                self._buf = []
            await self._ws.send(json.dumps({"message": "EndOfStream", "last_seq_no": self._seq}))
            await asyncio.wait_for(self._ended.wait(), 8)
        with contextlib.suppress(Exception):
            await self._ws.close()
        if self._reader:
            self._reader.cancel()


def make_transcriber(api_key: str, url: str) -> AgentTranscriber:
    return SpeechmaticsTranscriber(api_key, url) if api_key else NullTranscriber()
