"""Caller behaviour policies (SRS-FR-044) and CH-07 slow-caller pauses.

Each policy produces an observable audio-level effect and a call event, so its influence on metrics is
attributable. Pauses are inserted at deterministic positions (seeded ``policies`` stream).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from gauntlet.media.audio import silence_ms, voiced_span


@dataclass
class Built:
    pcm: np.ndarray
    segments: list[tuple[int, int]]
    text: str
    applied: list[str]


def split_for_pause(text: str) -> tuple[str, str] | None:
    words = text.split()
    if len(words) < 4:
        return None
    cut = max(2, len(words) // 2)
    return " ".join(words[:cut]), " ".join(words[cut:])


def join_with_pause(parts: list[np.ndarray], pause_ms: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Concatenate voiced parts with pauses; segments are the voiced spans of each part."""
    out: list[np.ndarray] = []
    segments: list[tuple[int, int]] = []
    pos = 0
    for i, p in enumerate(parts):
        if i:
            gap = silence_ms(pause_ms)
            out.append(gap)
            pos += len(gap)
        span = voiced_span(p)
        if span:
            segments.append((pos + span[0], pos + span[1]))
        out.append(p)
        pos += len(p)
    return (np.concatenate(out) if out else np.zeros(0, dtype=np.int16)), segments


def correction_due(policies: dict[str, Any], turn: int, done: set[str]) -> str | None:
    c = policies.get("correction") or {}
    if c.get("enabled") and "correction" not in done and turn >= int(c.get("after_turn", 2)):
        return str(c.get("text", "sorry, actually, let me correct that"))
    return None


def repetition_due(policies: dict[str, Any], turn: int, done: set[str]) -> bool:
    r = policies.get("repetition") or {}
    return bool(r.get("enabled")) and "repetition" not in done and turn >= int(r.get("after_turn", 3))


def hesitation_pause(policies: dict[str, Any], slow_caller_pause_ms: float) -> float:
    h = policies.get("hesitation") or {}
    pause = float(h.get("pause_ms", 0)) if h.get("enabled") else 0.0
    return max(pause, slow_caller_pause_ms)


def extended_silence_ms(policies: dict[str, Any]) -> float:
    e = policies.get("extended_silence") or {}
    return float(e.get("silence_ms", 0)) if e.get("enabled") else 0.0
