"""The reference agent's pipeline: speech-to-text -> language model -> text-to-speech.

A deliberately simple restaurant-booking agent ("Bella Tavola") built from hosted parts, so GAUNTLET has a
real pipeline with real, variable latency to measure and a conversation a referee can judge. Its
recogniser is Groq Whisper, which is independent of the referee (Speechmatics), as the methodology
requires. Documented as a test fixture: its quality says nothing about any product.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

import httpx
import numpy as np
import soundfile as sf

from gauntlet.caller.local_synth import synthesize_local
from gauntlet.media.audio import SAMPLE_RATE, time_stretch

SYSTEM = (
    "You are the phone booking assistant for Bella Tavola, an Italian restaurant. You only take, change and "
    "confirm table bookings (day, time, party size, name, dietary notes). Politely decline anything else and "
    "offer to help with a booking. Speak in one or two short sentences. When you have day, time, party size and "
    "name, read the full booking back to confirm it. Never use lists, markdown or emojis."
)
GREETING = "Thank you for calling Bella Tavola. How can I help you today?"


@dataclass
class ReferenceConfig:
    groq_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    groq_base: str = field(default_factory=lambda: os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    stt_model: str = field(default_factory=lambda: os.environ.get("REFERENCE_STT_MODEL", "whisper-large-v3-turbo"))
    llm_model: str = "llama-3.1-8b-instant"
    eleven_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", ""))
    eleven_voice: str = field(default_factory=lambda: os.environ.get("REFERENCE_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"))
    eleven_model: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"))
    use_eleven: bool = field(default_factory=lambda: os.environ.get("REFERENCE_TTS", "elevenlabs") == "elevenlabs")

    @property
    def available(self) -> bool:
        return bool(self.groq_key)


class ReferencePipeline:
    def __init__(self, cfg: ReferenceConfig | None = None, llm_model: str | None = None, rate: float = 1.0):
        self.cfg = cfg or ReferenceConfig()
        if llm_model:
            self.cfg.llm_model = llm_model
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
        r = await self._client.post(f"{self.cfg.groq_base}/chat/completions",
                                    headers={"Authorization": f"Bearer {self.cfg.groq_key}"},
                                    json={"model": self.cfg.llm_model, "messages": self.history[-20:],
                                          "temperature": 0.3, "max_tokens": 90})
        r.raise_for_status()
        text = str(r.json()["choices"][0]["message"]["content"]).strip() or "Sorry, could you say that again?"
        self.history.append({"role": "assistant", "content": text})
        return text

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
        pcm, _ = synthesize_local(text, "reference-agent", self.rate)
        return pcm

    async def turn(self, caller_pcm: np.ndarray) -> tuple[str, str, np.ndarray]:
        import time

        t0 = time.perf_counter()
        heard = await self.transcribe(caller_pcm)
        t1 = time.perf_counter()
        said = await self.reply(heard)
        t2 = time.perf_counter()
        pcm = await self.speak(said)
        t3 = time.perf_counter()
        self.last_timings = {"stt_ms": (t1 - t0) * 1000, "llm_ms": (t2 - t1) * 1000, "tts_ms": (t3 - t2) * 1000}
        return heard, said, pcm
