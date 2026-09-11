"""ARC-044 comparison and recommendation rules (SRS-FR-093, -094, PRD 12.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gauntlet.scoring.profile import ThresholdProfile


class IncompatibleRuns(Exception):
    def __init__(self, code: str, message: str, a: str, b: str):
        super().__init__(message)
        self.code = code
        self.a = a
        self.b = b


@dataclass
class RunSide:
    run_id: str
    suite_version_hash: str
    threshold_version_hash: str
    definitions_version: str
    metrics: dict[str, float | None]
    overall: float | None
    grade: str | None
    hard_breach: bool
    subscores: dict[str, float | None] = field(default_factory=dict)
    cost_per_successful_session: float | None = None
    label: str = ""


def check_compatible(a: RunSide, b: RunSide) -> None:
    if a.suite_version_hash != b.suite_version_hash:
        raise IncompatibleRuns("suite_mismatch", "runs executed different suite versions",
                               a.suite_version_hash, b.suite_version_hash)
    if a.threshold_version_hash != b.threshold_version_hash:
        raise IncompatibleRuns("threshold_mismatch", "runs were scored against different threshold profile versions",
                               a.threshold_version_hash, b.threshold_version_hash)
    if a.definitions_version != b.definitions_version:
        raise IncompatibleRuns("definitions_mismatch", "runs were computed with different metric definitions",
                               a.definitions_version, b.definitions_version)


def metric_rows(a: RunSide, b: RunSide, profile: ThresholdProfile) -> list[dict[str, Any]]:
    rows = []
    names = sorted(set(a.metrics) | set(b.metrics))
    for m in names:
        va, vb = a.metrics.get(m), b.metrics.get(m)
        bound = profile.bounds.get(m)
        row: dict[str, Any] = {"metric": m, "a": va, "b": vb,
                               "delta": round(vb - va, 6) if va is not None and vb is not None else None}
        if bound:
            row["threshold"] = bound.threshold
            row["direction"] = bound.direction
            for side, v in (("a_status", va), ("b_status", vb)):
                if v is None:
                    row[side] = "missing"
                else:
                    ok = v <= bound.threshold if bound.direction == "lower_is_better" else v >= bound.threshold
                    row[side] = "pass" if ok else "breach"
        rows.append(row)
    return rows


def recommend(a: RunSide, b: RunSide, band: float) -> dict[str, str]:
    """A = baseline, B = candidate. Ordered rule chain; the rule that fired is always returned."""
    if b.hard_breach and not a.hard_breach:
        return {"recommendation": "A", "rule_id": "R1",
                "rationale": "Candidate B has a hard breach and baseline A does not."}
    if a.overall is not None and b.overall is not None and b.overall - a.overall > band:
        return {"recommendation": "B", "rule_id": "R2",
                "rationale": f"B scores {b.overall - a.overall:.2f} points above A, more than the {band:g}-point band."}
    if (a.overall is not None and b.overall is not None and abs(b.overall - a.overall) <= band
            and a.cost_per_successful_session is not None and b.cost_per_successful_session is not None):
        cheaper = "A" if a.cost_per_successful_session <= b.cost_per_successful_session else "B"
        return {"recommendation": cheaper, "rule_id": "R3",
                "rationale": (f"Scores are within the {band:g}-point band, so the quality difference is within noise; "
                              f"{cheaper} has the lower estimated cost per successful session.")}
    return {"recommendation": "no_change", "rule_id": "R4",
            "rationale": "The difference does not justify a switch."}


def compare(a: RunSide, b: RunSide, profile: ThresholdProfile) -> dict[str, Any]:
    check_compatible(a, b)
    subs = sorted(set(a.subscores) | set(b.subscores))
    return {
        "a": {"run_id": a.run_id, "overall": a.overall, "grade": a.grade, "label": a.label},
        "b": {"run_id": b.run_id, "overall": b.overall, "grade": b.grade, "label": b.label},
        "metrics": metric_rows(a, b, profile),
        "subscores": [{"id": s, "a": a.subscores.get(s), "b": b.subscores.get(s)} for s in subs],
        "cost": {"a": a.cost_per_successful_session, "b": b.cost_per_successful_session,
                 "label": "estimated, based on your declared unit prices"},
        "recommendation": recommend(a, b, profile.comparison_band_points),
    }
