"""Bundled noise beds for CH-05 (SRS-FR-053).

The beds are *synthesised deterministically* from fixed seeds rather than recorded, so the repository
carries no binary audio and every run mixes bit-identical noise. They are engineered stand-ins for a
café and a street — distinguishable conditions, not acoustic reproductions of real places — and
docs/CONDITIONS.md says so.
"""

from __future__ import annotations

from functools import cache

import numpy as np

from gauntlet.media.audio import SAMPLE_RATE, to_int16

BED_SECONDS = 12
NOISE_BEDS = ("cafe", "street")


def _shaped_noise(rng: np.random.Generator, n: int, exponent: float) -> np.ndarray:
    """Noise with power spectrum ~ 1/f^exponent (1 = pink, 2 = brown), unit RMS."""
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    f[0] = f[1]
    spec *= 1.0 / np.power(f, exponent / 2.0)
    x = np.fft.irfft(spec, n)
    return x / (np.sqrt(np.mean(x * x)) + 1e-12)


def _bandpass(rng_noise: np.ndarray, lo: float, hi: float) -> np.ndarray:
    n = len(rng_noise)
    spec = np.fft.rfft(rng_noise)
    f = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.sqrt(np.mean(x * x)) + 1e-12)


def _cafe(rng: np.random.Generator, n: int) -> np.ndarray:
    t = np.arange(n) / SAMPLE_RATE
    bed = 0.5 * _shaped_noise(rng, n, 1.0)
    # distant babble: band-limited noise "voices" with syllabic (3-6 Hz) modulation
    for _ in range(6):
        voice = _bandpass(rng.standard_normal(n), 250, 3200)
        rate = rng.uniform(3.0, 6.0)
        phase = rng.uniform(0, 2 * np.pi)
        env = np.clip(np.sin(2 * np.pi * rate * t + phase), 0, None) ** 2
        env *= 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.1, 0.3) * t + rng.uniform(0, 6))
        bed += 0.35 * voice * env
    # cutlery clinks: short decaying high tones
    for _ in range(14):
        at = int(rng.uniform(0, n - 4000))
        k = np.arange(3000)
        bed[at : at + 3000] += 1.8 * np.sin(2 * np.pi * rng.uniform(3000, 5500) * k / SAMPLE_RATE) * np.exp(-k / 350.0)
    return bed


def _street(rng: np.random.Generator, n: int) -> np.ndarray:
    t = np.arange(n) / SAMPLE_RATE
    bed = 0.9 * _shaped_noise(rng, n, 2.0) + 0.25 * _shaped_noise(rng, n, 1.0)
    # passing vehicles: slow swells of low-mid broadband noise
    for _ in range(4):
        centre = rng.uniform(0, BED_SECONDS)
        width = rng.uniform(1.0, 2.5)
        swell = np.exp(-0.5 * ((t - centre) / width) ** 2)
        bed += 1.2 * _bandpass(rng.standard_normal(n), 60, 1200) * swell
    return bed


@cache
def noise_bed(name: str) -> np.ndarray:
    """A looped bed at -30 dBFS RMS. Level is irrelevant: the mixer scales it to the target SNR."""
    if name not in NOISE_BEDS:
        raise KeyError(f"unknown noise bed '{name}'")
    seed = {"cafe": 0xCAFE, "street": 0x57EE7}[name]
    rng = np.random.Generator(np.random.PCG64(seed))
    n = BED_SECONDS * SAMPLE_RATE
    x = _cafe(rng, n) if name == "cafe" else _street(rng, n)
    # 50 ms crossfade so the loop point is click-free
    fade = SAMPLE_RATE // 20
    ramp = np.linspace(0, 1, fade)
    x[:fade] = x[:fade] * ramp + x[-fade:] * (1 - ramp)
    x = x[: n - fade]
    target_rms = 32768.0 * 10 ** (-30 / 20)
    x = x / (np.sqrt(np.mean(x * x)) + 1e-12) * target_rms
    bed = to_int16(x)
    bed.setflags(write=False)
    return bed
