"""Run-level aggregation — nearest-rank percentiles and rollups (SRS 16.2, SRS-FR-061).

Nearest rank always returns an observed value, so a reader asking "which call produced the p95" gets
an answer. Samples below 20 are labelled low_sample wherever displayed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

LOW_SAMPLE = 20


def nearest_rank(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return float(ordered[rank - 1])


def mean(values: Sequence[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 3) if den else None


@dataclass
class MetricValue:
    name: str
    unit: str
    n: int
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    mean: float | None = None
    value: float | None = None
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def distribution(name: str, unit: str, values: Iterable[float | None]) -> MetricValue:
    vs = [float(v) for v in values if v is not None]
    mv = MetricValue(name, unit, len(vs), nearest_rank(vs, 50), nearest_rank(vs, 95), nearest_rank(vs, 99),
                     mean(vs))
    if len(vs) < LOW_SAMPLE:
        mv.flags.append("low_sample")
    return mv


@dataclass
class CallSummary:
    """The per-call facts aggregation needs, independent of storage."""

    status: str  # completed | failed | needs_review | errored
    attempt: int = 1
    turn_latencies: list[float] = field(default_factory=list)
    first_turn_latency: float | None = None
    barge_stops: list[float] = field(default_factory=list)  # applicable only, censored at 2000
    yields: int = 0
    applicable_interruptions: int = 0
    talkover_ms: float | None = None
    dead_air_ratio: float | None = None
    rig_overheads: list[float] = field(default_factory=list)
    turns: int = 0
    fallback_turns: int = 0
    premature_turns: int = 0
    cache_hits: int = 0
    utterances: int = 0
    task_success: bool | None = None
    scored: bool = False  # a verdict exists and is not scoring_failed
    needs_review: bool = False
    est_target_cost_usd: float | None = None


def aggregate(calls: Sequence[CallSummary]) -> dict[str, MetricValue]:
    """Roll per-call summaries into run metrics keyed by definitions.METRICS names."""
    out: dict[str, MetricValue] = {}
    total = len(calls)
    measurable = [c for c in calls if c.status != "errored"]  # errored calls excluded from percentiles

    lat = distribution("response_latency", "ms", [v for c in measurable for v in c.turn_latencies])
    for p in ("p50", "p95", "p99"):
        out[f"response_latency_{p}"] = MetricValue(f"response_latency_{p}", "ms", lat.n,
                                                   value=getattr(lat, p), flags=list(lat.flags))
    ttfr = distribution("time_to_first_response", "ms", [c.first_turn_latency for c in measurable])
    out["time_to_first_response_p50"] = MetricValue("time_to_first_response_p50", "ms", ttfr.n,
                                                     value=ttfr.p50, flags=list(ttfr.flags))

    stops = [v for c in measurable for v in c.barge_stops]
    applicable = sum(c.applicable_interruptions for c in measurable)
    if applicable:
        b = distribution("barge_in_stop", "ms", stops)
        censored = sum(1 for v in stops if v >= 2000)
        flags = list(b.flags) + ([f"censored:{censored}"] if censored else [])
        out["barge_in_stop_p95"] = MetricValue("barge_in_stop_p95", "ms", b.n, value=b.p95, flags=flags)
        out["yield_rate"] = MetricValue("yield_rate", "%", applicable,
                                        value=pct(sum(c.yields for c in measurable), applicable))

    talk = [c.talkover_ms for c in measurable if c.talkover_ms is not None]
    if talk:
        out["talkover_mean"] = MetricValue("talkover_mean", "ms", len(talk), value=round(mean(talk) or 0, 3))
    dead = [c.dead_air_ratio for c in measurable if c.dead_air_ratio is not None]
    if dead:
        out["dead_air_ratio"] = MetricValue("dead_air_ratio", "%", len(dead), value=round(mean(dead) or 0, 3))

    if total:
        errored = sum(1 for c in calls if c.status == "errored")
        out["call_completion_rate"] = MetricValue("call_completion_rate", "%", total, value=pct(total - errored, total))
        out["session_error_rate"] = MetricValue("session_error_rate", "%", total, value=pct(errored, total))
        out["reconnect_rate"] = MetricValue("reconnect_rate", "%", total,
                                            value=pct(sum(1 for c in calls if c.attempt > 1), total))

    scored = [c for c in measurable if c.scored]
    decided = [c for c in scored if not c.needs_review and c.task_success is not None]
    if decided:
        out["task_success_rate"] = MetricValue("task_success_rate", "%", len(decided),
                                               value=pct(sum(1 for c in decided if c.task_success), len(decided)))
    if scored:
        out["needs_review_rate"] = MetricValue("needs_review_rate", "%", len(scored),
                                               value=pct(sum(1 for c in scored if c.needs_review), len(scored)))

    rig = distribution("rig_overhead", "ms", [v for c in measurable for v in c.rig_overheads])
    if rig.n:
        out["rig_overhead_p95"] = MetricValue("rig_overhead_p95", "ms", rig.n, value=rig.p95, flags=rig.flags)
    turns = sum(c.turns for c in measurable)
    if turns:
        out["fallback_rate"] = MetricValue("fallback_rate", "%", turns,
                                           value=pct(sum(c.fallback_turns for c in measurable), turns))
        out["premature_speech_rate"] = MetricValue("premature_speech_rate", "%", turns,
                                                   value=pct(sum(c.premature_turns for c in measurable), turns))
    utts = sum(c.utterances for c in measurable)
    if utts:
        out["cache_hit_rate"] = MetricValue("cache_hit_rate", "%", utts,
                                            value=pct(sum(c.cache_hits for c in measurable), utts))

    costs = [c.est_target_cost_usd for c in measurable if c.est_target_cost_usd is not None]
    if costs:
        total_cost = sum(costs)
        out["est_cost_per_session"] = MetricValue("est_cost_per_session", "USD", len(costs),
                                                  value=round(total_cost / len(costs), 6))
        successes = sum(1 for c in decided if c.task_success)
        out["est_cost_per_successful_session"] = MetricValue(
            "est_cost_per_successful_session", "USD", successes,
            value=round(total_cost / successes, 6) if successes else None,
            flags=[] if successes else ["undefined_no_successful_sessions"],
        )
    return out


def completed_calls(calls: Sequence[CallSummary]) -> int:
    """Calls that reached a terminal non-errored state — the sample-size basis for grading."""
    return sum(1 for c in calls if c.status in ("completed", "failed", "needs_review"))
