"""ARC-032 interruption scheduler (SRS-FR-043).

Offsets are drawn from the call's seeded ``interrupts`` stream *before the call starts* and persisted
on the call row. During the call the caller begins transmitting exactly at
``agent_speech_onset + offset_ms`` for the scheduled turn. The model has no say in the timing, so
interruption offsets reproduce byte-for-byte across identically seeded runs.
"""

from __future__ import annotations

from typing import Any

from gauntlet.common import seeds

DEFAULT_LINES = ["Sorry, wait, hold on.", "Hang on a second.", "Sorry, just a moment."]


def interruptions_for(persona: dict[str, Any], profile_count: int) -> int:
    """Profile sets the count (CH-06); persona tendency can add one, deterministically."""
    tendency = float(persona.get("interruption_tendency", 0.0))
    extra = 1 if profile_count > 0 and tendency >= 0.6 else 0
    return min(5, profile_count + extra)


def schedule(call_seed: int, count: int, offset_range_ms: tuple[float, float], max_turns: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    r = seeds.rng(call_seed, "interrupts")
    candidates = list(range(1, max(2, min(max_turns, 7))))
    turns = sorted(int(t) for t in r.choice(candidates, size=min(count, len(candidates)), replace=False))
    lo, hi = offset_range_ms
    return [{"turn_idx": t, "offset_ms": round(float(r.uniform(lo, hi)), 3)} for t in turns]
