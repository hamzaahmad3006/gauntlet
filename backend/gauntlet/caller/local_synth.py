"""Bundled local synthesiser — the last fallback for caller audio (SRS 1.6: cache, then local).

If ``espeak-ng`` (or ``espeak``) is installed, it produces intelligible speech. Otherwise a deterministic
"babble" generator produces speech-shaped audio: voiced syllables with harmonic structure and formant
colouring, consonant bursts, word gaps and punctuation pauses, with duration driven by text length and
speech rate. Babble is not intelligible; it exists so the rig can exercise energy-based fixtures with no
provider at all, and docs/LIMITATIONS.md says so.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess

import numpy as np
import soundfile as sf

from gauntlet.media.audio import SAMPLE_RATE, resample_linear, to_int16

VOWELS = [(730, 1090), (270, 2290), (530, 1840), (570, 840), (300, 870), (660, 1720), (490, 1350)]


def _rng_for(text: str, voice_id: str) -> np.random.Generator:
    seed = int.from_bytes(hashlib.sha256(f"{voice_id}|{text}".encode()).digest()[:8], "big")
    return np.random.Generator(np.random.PCG64(seed))


def _f0_for(voice_id: str) -> float:
    h = int.from_bytes(hashlib.sha256(voice_id.encode()).digest()[:2], "big")
    return 105.0 + (h % 1000) / 1000.0 * 115.0  # 105..220 Hz


def babble(text: str, voice_id: str = "default", rate: float = 1.0, level_dbfs: float = -22.0) -> np.ndarray:
    rng = _rng_for(text, voice_id)
    f0_base = _f0_for(voice_id)
    tokens = re.findall(r"[A-Za-z0-9']+|[,.;:?!]", text) or ["uh"]
    parts: list[np.ndarray] = [np.zeros(int(0.03 * SAMPLE_RATE))]
    n_words = sum(1 for t in tokens if t[0].isalnum())
    w = 0
    for tok in tokens:
        if not tok[0].isalnum():
            pause = {",": 0.18, ";": 0.22, ":": 0.2}.get(tok, 0.32)
            parts.append(np.zeros(int(pause / rate * SAMPLE_RATE)))
            continue
        syllables = max(1, round(len(tok) / 3.2))
        for _ in range(syllables):
            # declining intonation across the utterance
            f0 = f0_base * (1.1 - 0.2 * (w / max(1, n_words))) * rng.uniform(0.95, 1.05)
            cons_n = int(rng.uniform(0.015, 0.04) / rate * SAMPLE_RATE)
            cons = rng.standard_normal(cons_n) * 0.25
            cons = np.diff(cons, prepend=0.0)  # crude high-pass: fricative colour
            vow_n = int(rng.uniform(0.11, 0.19) / rate * SAMPLE_RATE)
            t = np.arange(vow_n) / SAMPLE_RATE
            f1, f2 = VOWELS[int(rng.integers(0, len(VOWELS)))]
            vowel = np.zeros(vow_n)
            for h in range(1, 16):
                fh = h * f0
                if fh > 3800:
                    break
                gain = np.exp(-((fh - f1) / 180.0) ** 2) + 0.6 * np.exp(-((fh - f2) / 250.0) ** 2) + 0.05 / h
                vowel += gain * np.sin(2 * np.pi * fh * t + rng.uniform(0, 2 * np.pi))
            env = np.minimum(1.0, np.minimum(t / 0.012, (t[-1] - t + 1e-3) / 0.03))
            parts += [cons, vowel * env]
        w += 1
        parts.append(np.zeros(int(rng.uniform(0.04, 0.09) / rate * SAMPLE_RATE)))
    x = np.concatenate(parts)
    voiced = x[np.abs(x) > 1e-4]
    rms = float(np.sqrt(np.mean(voiced**2))) if voiced.size else 1.0
    x = x / (rms + 1e-12) * 32768.0 * 10 ** (level_dbfs / 20)
    return to_int16(x)


def espeak_binary() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def espeak(text: str, rate: float = 1.0) -> np.ndarray | None:
    exe = espeak_binary()
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "-v", "en-us", "-s", str(int(165 * rate)), "--stdout", text],
                             capture_output=True, timeout=10, check=True).stdout
        data, sr = sf.read(io.BytesIO(out), dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        return resample_linear(data, sr, SAMPLE_RATE)
    except (subprocess.SubprocessError, OSError, RuntimeError):
        return None


def synthesize_local(text: str, voice_id: str, rate: float) -> tuple[np.ndarray, str]:
    pcm = espeak(text, rate)
    if pcm is not None and len(pcm):
        return pcm, "espeak"
    return babble(text, voice_id, rate), "babble"
