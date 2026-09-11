"""ARC-042 scoring engine — deterministic composite readiness score (SRS-FR-091, -092, SRS 19).

``score(metrics, profile, completed_calls)`` is a pure function: no clock, no randomness, no network,
no model. Recomputation from stored metrics reproduces the result exactly.

Missing data (SRS 19.6, narrowed by deviation D-14): a missing *input* redistributes its intra-weight
across the sub-score's remaining inputs and flags ``partial_scoring`` naming the metric; a sub-score
with no available inputs is ``unavailable`` and its weight is redistributed across the remaining
sub-scores. Two or more unavailable sub-scores suppress the grade entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from gauntlet.scoring.normalise import CTX, D, normalise, q2
from gauntlet.scoring.profile import ThresholdProfile

GRADES = (("A", 90), ("B", 80), ("C", 70), ("D", 60), ("F", 0))


def grade_for(overall: Decimal) -> str:
    for g, lo in GRADES:
        if overall >= lo:
            return g
    return "F"


@dataclass
class InputContribution:
    metric: str
    value: float | None
    normalised: float | None
    intra_weight: float
    effective_weight: float
    status: str  # pass | breach | missing


@dataclass
class SubScore:
    id: str
    name: str
    weight: float
    effective_weight: float
    score: float | None
    available: bool
    inputs: list[InputContribution]
    contribution: float | None = None


@dataclass
class ScoreResult:
    overall: float | None
    grade: str | None
    subscores: list[SubScore]
    flags: list[str] = field(default_factory=list)
    caps: list[str] = field(default_factory=list)
    suppressed_reason: str | None = None
    missing_metrics: list[str] = field(default_factory=list)
    profile_key: str = ""
    profile_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "grade": self.grade,
            "flags": self.flags,
            "caps": self.caps,
            "suppressed_reason": self.suppressed_reason,
            "missing_metrics": self.missing_metrics,
            "profile_key": self.profile_key,
            "profile_version": self.profile_version,
            "subscores": [
                {**{k: v for k, v in s.__dict__.items() if k != "inputs"},
                 "inputs": [i.__dict__ for i in s.inputs]}
                for s in self.subscores
            ],
        }


def score(metrics: dict[str, float | None], profile: ThresholdProfile, completed_calls: int,
          min_calls: int | None = None) -> ScoreResult:
    min_calls = int(profile.hard_breaches.get("min_completed_calls", 20) if min_calls is None else min_calls)
    result = ScoreResult(None, None, [], profile_key=profile.key, profile_version=profile.version_hash)

    # 1. sub-scores with intra-sub-score redistribution of missing inputs
    for sdef in profile.subscores:
        present = {m: w for m, w in sdef.inputs.items() if metrics.get(m) is not None}
        inputs: list[InputContribution] = []
        total_w = sum(present.values())
        acc = D(0)
        for m, w in sdef.inputs.items():
            v = metrics.get(m)
            if v is None:
                inputs.append(InputContribution(m, None, None, w, 0.0, "missing"))
                if m not in result.missing_metrics:
                    result.missing_metrics.append(m)
                continue
            bound = profile.bounds[m]
            n = normalise(float(v), bound)
            ew = CTX.divide(D(w), D(total_w))
            acc = CTX.add(acc, CTX.multiply(n, ew))
            ok = float(v) <= bound.threshold if bound.direction == "lower_is_better" else float(v) >= bound.threshold
            inputs.append(InputContribution(m, float(v), float(n), w, float(q2(ew)), "pass" if ok else "breach"))
        available = bool(present)
        result.subscores.append(SubScore(sdef.id, sdef.name, sdef.weight, 0.0, float(q2(acc)) if available else None,
                                         available, inputs))

    if result.missing_metrics:
        result.flags.append("partial_scoring")

    # 2. sample-size suppression (PRD 12.5) — no grade from a sample too small to support one
    if completed_calls < min_calls:
        result.suppressed_reason = f"insufficient_sample: {completed_calls} completed calls, minimum {min_calls}"
        result.flags.append("insufficient_sample")
        return result

    unavailable = [s for s in result.subscores if not s.available]
    if len(unavailable) >= 2:
        names = ", ".join(f"{s.id} {s.name}" for s in unavailable)
        result.suppressed_reason = f"two_or_more_subscores_unavailable: {names}"
        return result

    # 3. overall with proportional redistribution of an unavailable sub-score's weight
    avail_w = sum(s.weight for s in result.subscores if s.available)
    overall = D(0)
    for s in result.subscores:
        if not s.available:
            continue
        ew = CTX.divide(D(s.weight), D(avail_w))
        s.effective_weight = float(q2(ew))
        contrib = CTX.multiply(D(s.score), ew)
        s.contribution = float(q2(contrib))
        overall = CTX.add(overall, contrib)
    overall = q2(overall)
    result.overall = float(overall)
    result.grade = grade_for(overall)

    # 4. hard-breach caps (SRS 19.5): a fatal flaw cannot be averaged away
    hb = profile.hard_breaches
    checks = [
        ("call_completion_rate", "call_completion_rate_min", "call completion rate"),
        ("yield_rate", "yield_rate_min", "yield rate"),
        ("task_success_rate", "task_success_rate_min", "task success rate"),
    ]
    for metric, key, label in checks:
        v = metrics.get(metric)
        if v is not None and key in hb and float(v) < hb[key]:
            result.caps.append(f"{label} {v:g}% below hard limit {hb[key]:g}%")
    if result.caps:
        result.grade = "F"
        result.flags.append("hard_breach")
    return result


def recompute_matches(stored: dict[str, Any], metrics: dict[str, float | None], profile: ThresholdProfile,
                      completed_calls: int) -> bool:
    """TC-091: the stored score must be reproducible bit-for-bit from stored metrics."""
    fresh = score(metrics, profile, completed_calls).as_dict()
    return fresh == stored
