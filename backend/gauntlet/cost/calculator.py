"""ARC-043 cost calculator (SRS-FR-080..082, SRS 20).

Rig cost is MEASURED: provider-returned counters x operator-supplied prices. Target cost is ESTIMATED:
a model over measured session characteristics and the target owner's declared prices. The two are never
summed, never share a column, and carry distinct labels everywhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from gauntlet.common.paths import CONFIG_DIR

UNITS = {"per_1k_tokens", "per_1k_characters", "per_minute", "per_second", "per_call", "per_hour"}
DEFAULT_PRICING_PATH = CONFIG_DIR / "pricing.yaml"


@dataclass
class PriceEntry:
    price: float
    unit: str
    currency: str = "USD"
    source: str = ""
    retrieved_at: str = ""

    def stale(self, today: date | None = None) -> bool:
        try:
            d = datetime.strptime(self.retrieved_at, "%Y-%m-%d").date()
        except ValueError:
            return True
        return ((today or date.today()) - d).days > 90


@dataclass
class Pricing:
    entries: dict[str, dict[str, PriceEntry]]
    unknown_unit_cost_usd: float = 0.01
    warnings: list[str] = field(default_factory=list)

    def get(self, provider: str, counter: str) -> PriceEntry | None:
        return self.entries.get(provider, {}).get(counter)

    @property
    def configured(self) -> bool:
        return any(e.price > 0 for p in self.entries.values() for e in p.values())


def load_pricing(path: Path | str | None = None) -> Pricing:
    p = Path(path) if path else DEFAULT_PRICING_PATH
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    entries: dict[str, dict[str, PriceEntry]] = {}
    warnings: list[str] = []
    for provider, counters in (doc.get("providers") or {}).items():
        entries[provider] = {}
        for counter, spec in (counters or {}).items():
            if not isinstance(spec, dict):
                continue  # e.g. "model:" annotation
            e = PriceEntry(float(spec.get("price", 0.0)), str(spec.get("unit")), str(spec.get("currency", "USD")),
                           str(spec.get("source", "")), str(spec.get("retrieved_at", "")))
            if e.unit not in UNITS:
                raise ValueError(f"pricing {provider}.{counter}: unit '{e.unit}' not in {sorted(UNITS)}")
            if e.price < 0:
                raise ValueError(f"pricing {provider}.{counter}: negative price")
            if e.stale():
                warnings.append(f"pricing {provider}.{counter} retrieved_at {e.retrieved_at or 'unset'} is older than 90 days")
            entries[provider][counter] = e
    unknown = float((doc.get("defaults") or {}).get("unknown_unit_cost_usd", 0.01))
    return Pricing(entries, unknown, warnings)


@dataclass
class RigCounters:
    """Everything the rig spent, as counted. Stored so recomputation is exact (TC-080)."""

    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_calls_unpriced: int = 0
    tts_characters: int = 0  # cache misses only
    stt_audio_seconds: float = 0.0
    media_participant_minutes: float = 0.0
    scorer_prompt_tokens: int = 0
    scorer_completion_tokens: int = 0

    def add(self, other: RigCounters) -> None:
        for k in self.__dict__:
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _charge(entry: PriceEntry | None, amount: float, base: str, fallback: float, notes: list[str],
            label: str) -> float:
    """Price ``amount`` measured in ``base`` (tokens | characters | seconds | minutes) at the entry's unit."""
    if entry is None:
        if amount:
            notes.append(f"{label}: no price configured, charged at unknown_unit_cost_usd")
            return fallback
        return 0.0
    u = entry.unit
    if u in ("per_1k_tokens", "per_1k_characters"):
        return amount / 1000.0 * entry.price
    seconds = amount * 60.0 if base == "minutes" else amount
    if u == "per_second":
        return seconds * entry.price
    if u == "per_minute":
        return seconds / 60.0 * entry.price
    if u == "per_hour":
        return seconds / 3600.0 * entry.price
    return entry.price if amount else 0.0  # per_call


def rig_cost(c: RigCounters, pricing: Pricing) -> dict[str, Any]:
    """SRS 20.2. Returns total and per-provider breakdown; deterministic from counters."""
    notes: list[str] = []
    fb = pricing.unknown_unit_cost_usd
    llm = (_charge(pricing.get("caller_llm", "prompt_tokens"), c.llm_prompt_tokens + c.scorer_prompt_tokens,
                   "tokens", fb, notes, "llm prompt")
           + _charge(pricing.get("caller_llm", "completion_tokens"), c.llm_completion_tokens + c.scorer_completion_tokens,
                     "tokens", fb, notes, "llm completion")
           + c.llm_calls_unpriced * fb)
    tts = _charge(pricing.get("caller_tts", "characters"), c.tts_characters, "characters", fb, notes, "tts")
    stt = _charge(pricing.get("referee_stt", "audio_seconds"), c.stt_audio_seconds, "seconds", fb, notes, "stt")
    media = _charge(pricing.get("media", "participant_minutes"), c.media_participant_minutes, "minutes", fb, notes,
                    "media")
    breakdown = {"caller_llm": round(llm, 6), "caller_tts": round(tts, 6), "referee_stt": round(stt, 6),
                 "media": round(media, 6)}
    flags = [] if pricing.configured else ["pricing_not_configured"]
    return {"total_usd": round(sum(breakdown.values()), 6), "breakdown": breakdown, "notes": notes, "flags": flags,
            "counters": c.as_dict()}


@dataclass
class SessionShape:
    agent_audio_seconds: float
    caller_audio_seconds: float
    agent_transcript_chars: int
    caller_text_chars: int


def estimate_target_cost(shape: SessionShape, declaration: dict[str, Any] | None,
                         context_factor: float = 1.5) -> dict[str, Any] | None:
    """SRS 20.4. None when nothing is declared — no estimated target cost may appear anywhere then."""
    if not declaration:
        return None
    prices = declaration.get("unit_prices") or declaration
    llm = prices.get("llm") or {}
    tts = prices.get("tts") or {}
    stt = prices.get("stt") or {}
    undeclared = [k for k, v in (("llm", llm), ("tts", tts), ("stt", stt)) if not v]
    tokens_out = math.ceil(shape.agent_transcript_chars / 4)
    tokens_in = math.ceil((shape.caller_text_chars + shape.agent_transcript_chars) / 4) * context_factor
    cost = (tokens_in / 1000 * float(llm.get("prompt_price_per_1k_tokens", 0))
            + tokens_out / 1000 * float(llm.get("completion_price_per_1k_tokens", 0))
            + shape.agent_transcript_chars / 1000 * float(tts.get("price_per_1k_characters", 0))
            + shape.caller_audio_seconds / 60 * float(stt.get("price_per_minute", 0)))
    return {
        "estimated_usd": round(cost, 6),
        "label": "estimated, based on your declared unit prices",
        "undeclared_components": undeclared,
        "assumptions": {"chars_per_token": 4, "context_factor": context_factor},
        "inputs": shape.__dict__,
    }
