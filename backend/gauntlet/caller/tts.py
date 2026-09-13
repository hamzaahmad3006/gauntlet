"""ARC-031 speech synthesis client with content-hash cache (SRS-FR-042, -055, SRS 29 circuit breaker).

Cache key: sha256(text | voice | rate | provider | model). A repeated utterance costs zero provider
calls. Fallback order: provider -> cache -> bundled local synthesiser, and every substitution is recorded
on the result so a run is never silently different from its baseline.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from gauntlet.caller.local_synth import synthesize_local
from gauntlet.common.clock import now_ns
from gauntlet.common.paths import CACHE_DIR
from gauntlet.media.audio import time_stretch

ELEVEN_RATE_RANGE = (0.7, 1.2)


@dataclass
class SynthResult:
    pcm: np.ndarray
    cached: bool
    provider: str
    model: str
    voice_id: str
    characters: int  # billable characters (0 on a cache hit)
    synthesis_ms: float
    rate_applied_locally: bool = False
    voice_substituted: bool = False
    fallback: str | None = None  # why the provider was not used, if it was not


class CircuitBreaker:
    def __init__(self, threshold: int = 5, open_s: float = 30.0):
        self.threshold, self.open_s = threshold, open_s
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.open_s:
            self.opened_at = None  # half-open: next call is a trial
            self.failures = self.threshold - 1
            return False
        return True

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


class SpeechSynth:
    def __init__(self, api_key: str = "", model: str = "eleven_flash_v2_5", default_voice: str = "",
                 cache_dir: Path | None = None, timeout_s: float = 8.0):
        self.api_key = api_key
        self.model = model
        self.default_voice = default_voice
        self.cache_dir = (cache_dir or CACHE_DIR / "tts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.breaker = CircuitBreaker()
        self._client: httpx.AsyncClient | None = None
        self._bad_voices: set[str] = set()

    @property
    def provider(self) -> str:
        return "elevenlabs" if self.api_key else "local"

    def _key(self, text: str, voice: str, rate: float, provider: str, model: str) -> str:
        return hashlib.sha256(f"{text}|{voice}|{rate:.3f}|{provider}|{model}".encode()).hexdigest()

    def _cache_get(self, key: str) -> np.ndarray | None:
        p = self.cache_dir / f"{key}.pcm"
        if not p.exists():
            return None
        data = p.read_bytes()
        if len(data) < 64 or data[:64] != key.encode()[:64]:
            return None  # corrupted entry — key is stored as a header so corruption is detectable
        return np.frombuffer(data[64:], dtype="<i2").astype(np.int16)

    def _cache_put(self, key: str, pcm: np.ndarray) -> None:
        tmp = self.cache_dir / f"{key}.tmp"
        tmp.write_bytes(key.encode()[:64] + pcm.astype("<i2").tobytes())
        tmp.replace(self.cache_dir / f"{key}.pcm")

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()

    async def synthesize(self, text: str, voice_id: str, rate: float = 1.0) -> SynthResult:
        t0 = now_ns()
        provider = self.provider
        model = self.model if provider == "elevenlabs" else "local"
        voice = voice_id if voice_id not in self._bad_voices else (self.default_voice or voice_id)
        substituted = voice != voice_id
        key = self._key(text, voice, rate, provider, model)
        hit = self._cache_get(key)
        if hit is not None:
            return SynthResult(hit, True, provider, model, voice, 0, (now_ns() - t0) / 1e6,
                               voice_substituted=substituted)
        fallback = None
        if provider == "elevenlabs" and not self.breaker.open:
            try:
                pcm, local_rate = await self._elevenlabs(text, voice, rate)
                self.breaker.success()
                self._cache_put(key, pcm)
                return SynthResult(pcm, False, provider, model, voice, len(text), (now_ns() - t0) / 1e6,
                                   rate_applied_locally=local_rate, voice_substituted=substituted)
            except _VoiceUnavailable:
                self._bad_voices.add(voice_id)
                if self.default_voice and voice != self.default_voice:
                    return await self.synthesize(text, voice_id, rate)
                fallback = "voice_unavailable"
            except Exception as e:  # provider error: breaker counts it, caller gets local audio
                self.breaker.failure()
                fallback = f"provider_error:{type(e).__name__}"
        elif provider == "elevenlabs":
            fallback = "circuit_open"
        # local synthesiser, cached under its own provider key
        lkey = self._key(text, voice, rate, "local", "local")
        pcm = self._cache_get(lkey)
        cached = pcm is not None
        engine = "local"
        if pcm is None:
            pcm, engine = await asyncio.to_thread(synthesize_local, text, voice, rate)
            self._cache_put(lkey, pcm)
        return SynthResult(pcm, cached, "local", engine, voice, 0, (now_ns() - t0) / 1e6,
                           voice_substituted=substituted, fallback=fallback)

    async def _elevenlabs(self, text: str, voice: str, rate: float) -> tuple[np.ndarray, bool]:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        lo, hi = ELEVEN_RATE_RANGE
        provider_rate = min(max(rate, lo), hi)
        r = await self._client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            params={"output_format": "pcm_16000"},
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": self.model,
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": provider_rate}},
        )
        # 402: the account's plan cannot use this voice through the API (free plans exclude library voices)
        if (r.status_code in (400, 404) and "voice" in r.text.lower()) or r.status_code == 402:
            raise _VoiceUnavailable()
        r.raise_for_status()
        pcm = np.frombuffer(r.content[: len(r.content) // 2 * 2], dtype="<i2").astype(np.int16)
        local = False
        if abs(rate - provider_rate) > 1e-3:  # SRS-FR-055: rate outside provider range applied locally
            pcm = time_stretch(pcm, rate / provider_rate)
            local = True
        return pcm, local


class _VoiceUnavailable(Exception):
    pass
