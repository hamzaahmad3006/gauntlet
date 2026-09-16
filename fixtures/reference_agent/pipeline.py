"""The reference agent's pipeline: speech-to-text -> language model -> text-to-speech.

A deliberately simple restaurant-booking agent ("Bella Tavola") built from hosted parts, so GAUNTLET has a
real pipeline with real, variable latency to measure and a conversation a referee can judge. Its
recogniser is Groq Whisper, which is independent of the referee (Speechmatics), as the methodology
requires. Documented as a test fixture: its quality says nothing about any product.
"""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass, field

import httpx
import numpy as np
import soundfile as sf

from gauntlet.caller.local_synth import synthesize_local
from gauntlet.common.llm import FALLBACK_MODEL, reasoning_params, resolve_model
from gauntlet.media.audio import SAMPLE_RATE, time_stretch

log = logging.getLogger("gauntlet.fixture.agent")

SYSTEM = (
    "You are the phone booking assistant for Bella Tavola, an Italian restaurant. You only take, change and "
    "confirm table bookings (day, time, party size, name, dietary notes). Politely decline anything else and "
    "offer to help with a booking. Speak in one or two short sentences. When you have day, time, party size and "
    "name, read the full booking back to confirm it. Never use lists, markdown or emojis."
)
GREETING = "Thank you for calling Bella Tavola. How can I help you today?"


def _setting(env: str, attr: str, default: str = "") -> str:
    """Environment first, then GAUNTLET settings (which also read .env), so the bundled agent in the API
    process sees the same provider keys as the rig."""
    if os.environ.get(env):
        return os.environ[env]
    try:
        from gauntlet.common.settings import get_settings

        return str(getattr(get_settings(), attr) or default)
    except Exception:
        return default


@dataclass
class ReferenceConfig:
    groq_key: str = field(default_factory=lambda: _setting("GROQ_API_KEY", "groq_api_key"))
    groq_base: str = field(default_factory=lambda: _setting("GROQ_BASE_URL", "groq_base_url",
                                                            "https://api.groq.com/openai/v1"))
    stt_model: str = field(default_factory=lambda: os.environ.get("REFERENCE_STT_MODEL", "whisper-large-v3-turbo"))
    llm_model: str = "openai/gpt-oss-20b"
    eleven_key: str = field(default_factory=lambda: _setting("ELEVENLABS_API_KEY", "elevenlabs_api_key"))
    eleven_voice: str = field(default_factory=lambda: os.environ.get("REFERENCE_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"))
    eleven_model: str = field(default_factory=lambda: _setting("ELEVENLABS_MODEL", "elevenlabs_model",
                                                               "eleven_flash_v2_5"))
    use_eleven: bool = field(default_factory=lambda: os.environ.get("REFERENCE_TTS", "elevenlabs") == "elevenlabs")

    @property
    def available(self) -> bool:
        return bool(self.groq_key)


class ReferencePipeline:
    def __init__(self, cfg: ReferenceConfig | None = None, llm_model: str | None = None, rate: float = 1.0):
        self.cfg = cfg or ReferenceConfig()
        if llm_model:
            self.cfg.llm_model = resolve_model(llm_model)
        self.rate = rate
        self.history: list[dict[str, str]] = [{"role": "system", "content": SYSTEM}]
        self._client = httpx.AsyncClient(timeout=20)
        self.last_timings: dict[str, float] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, pcm: np.ndarray) -> str:
        buf = io.BytesIO()
        sf.write(buf, pcm, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        r = await self._client.post(f"{self.cfg.groq_base}/audio/transcriptions",
                                    headers={"Authorization": f"Bearer {self.cfg.groq_key}"},
                                    files={"file": ("utterance.wav", buf.getvalue(), "audio/wav")},
                                    data={"model": self.cfg.stt_model, "response_format": "json", "language": "en",
                                          "temperature": "0"})
        r.raise_for_status()
        return str(r.json().get("text", "")).strip()

    async def reply(self, caller_text: str) -> str:
        self.history.append({"role": "user", "content": caller_text or "(inaudible)"})
        r = await self._ask(self.cfg.llm_model)
        if r.status_code == 404 and self.cfg.llm_model != FALLBACK_MODEL:  # the model left the catalogue
            log.warning("model %s is gone; falling back to %s", self.cfg.llm_model, FALLBACK_MODEL)
            self.cfg.llm_model = FALLBACK_MODEL
            r = await self._ask(FALLBACK_MODEL)
        r.raise_for_status()
        text = str(r.json()["choices"][0]["message"]["content"]).strip() or "Sorry, could you say that again?"
        self.history.append({"role": "assistant", "content": text})
        return text

    async def _ask(self, model: str):
        return await self._client.post(f"{self.cfg.groq_base}/chat/completions",
                                       headers={"Authorization": f"Bearer {self.cfg.groq_key}"},
                                       json={"model": model, "messages": self.history[-20:],
                                             "temperature": 0.3, "max_tokens": 300, **reasoning_params(model)})

    async def speak(self, text: str) -> np.ndarray:
        if self.cfg.eleven_key and self.cfg.use_eleven:
            try:
                r = await self._client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self.cfg.eleven_voice}",
                    params={"output_format": "pcm_16000"},
                    headers={"xi-api-key": self.cfg.eleven_key},
                    json={"text": text, "model_id": self.cfg.eleven_model,
                          "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
                r.raise_for_status()
                pcm = np.frombuffer(r.content[: len(r.content) // 2 * 2], dtype="<i2").astype(np.int16)
                return time_stretch(pcm, self.rate) if abs(self.rate - 1) > 1e-3 else pcm
            except Exception:
                pass
        import asyncio

        pcm, _ = await asyncio.to_thread(synthesize_local, text, "reference-agent", self.rate)  # never on the loop
        return pcm

    async def turn(self, caller_pcm: np.ndarray) -> tuple[str, str | None, np.ndarray | None]:
        import time

        t0 = time.perf_counter()
        # The utterance carries pre-roll and the endpointing silence, so judge it by its voiced frames. The
        # loudness of a real microphone varies hugely between laptops, so "voiced" is relative to this
        # utterance's own peak rather than a fixed level: under 160 ms of sound is a knock or a breath.
        frames = caller_pcm[: len(caller_pcm) // 320 * 320].astype(np.float32).reshape(-1, 320)
        levels = np.sqrt((frames ** 2).mean(axis=1)) if len(frames) else np.zeros(0)
        floor = max(120.0, 0.18 * float(levels.max())) if levels.size else 0.0
        loud = np.nonzero(levels > floor)[0]
        voiced = int(loud.size)
        log.info("caller utterance: %d frames, %d voiced above %.0f, peak %.0f",
                 len(levels), voiced, floor, float(levels.max()) if levels.size else 0)
        if voiced < 8:
            return "", None, None
        # send only the spoken span, with a little air either side: recognisers invent sentences when they
        # are handed seconds of near-silence
        a = max(0, int(loud[0]) - 8) * 320
        b = min(len(frames), int(loud[-1]) + 9) * 320
        heard = await self.transcribe(caller_pcm[a:b])
        t1 = time.perf_counter()
        log.info("heard in %.0f ms: %r", (t1 - t0) * 1000, heard)
        # a word needs a vowel: "Mmm", "Hmm." and bare punctuation are throat-clearing, not a turn
        if not any(set(w.lower()) & set("aeiou") for w in re.findall(r"[A-Za-z]{2,}", heard)):
            self.last_timings = {"stt_ms": (t1 - t0) * 1000}
            log.info("no words in %r: staying silent", heard)
            return heard, None, None
        said = await self.reply(heard)
        t2 = time.perf_counter()
        pcm = await self.speak(said)
        t3 = time.perf_counter()
        self.last_timings = {"stt_ms": (t1 - t0) * 1000, "llm_ms": (t2 - t1) * 1000, "tts_ms": (t3 - t2) * 1000}
        log.info("replying in %.0f ms: %r", (t3 - t1) * 1000, said)
        return heard, said, pcm
