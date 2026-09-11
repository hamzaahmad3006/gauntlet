"""Gate evaluation and Markdown rendering (SRS-FR-096, -097, PRD 12.7).

A gate fails if: the overall score dropped by more than the tolerance; any metric crossed from passing
to breaching its threshold; a hard breach is present. An aborted, budget-aborted or low-sample
candidate is ungatable — a distinct outcome from a failure, so CI can tell an outage from a regression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gauntlet.scoring.compare import RunSide, check_compatible
from gauntlet.scoring.profile import ThresholdProfile

MARKER = "<!-- gauntlet-gate -->"
UNGATABLE_STATUSES = {"aborted", "aborted_budget", "failed"}


class Ungatable(Exception):
    pass


@dataclass
class GateResult:
    verdict: str  # passed | failed
    breaches: list[dict[str, Any]] = field(default_factory=list)
    markdown: str = ""
    score_delta: float | None = None


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:.3g}"
    return str(v)


def evaluate(candidate: RunSide, baseline: RunSide, profile: ThresholdProfile, tolerance: float | None = None,
             candidate_status: str = "completed", candidate_flags: list[str] | None = None,
             report_url: str | None = None) -> GateResult:
    flags = candidate_flags or []
    if candidate_status in UNGATABLE_STATUSES or "insufficient_sample" in flags or candidate.overall is None:
        raise Ungatable(f"candidate run is not gatable (status={candidate_status}, flags={','.join(flags) or 'none'})")
    check_compatible(baseline, candidate)
    tol = profile.gate_tolerance_points if tolerance is None else tolerance
    breaches: list[dict[str, Any]] = []

    delta = None
    if baseline.overall is not None:
        delta = round(candidate.overall - baseline.overall, 2)
        if delta < -tol:
            breaches.append({"kind": "score_drop", "metric": "readiness", "baseline": baseline.overall,
                             "candidate": candidate.overall, "delta": delta, "tolerance": tol})

    for m, bound in profile.bounds.items():
        vb, vc = baseline.metrics.get(m), candidate.metrics.get(m)
        if vc is None:
            continue
        c_ok = vc <= bound.threshold if bound.direction == "lower_is_better" else vc >= bound.threshold
        b_ok = True if vb is None else (vb <= bound.threshold if bound.direction == "lower_is_better"
                                        else vb >= bound.threshold)
        if b_ok and not c_ok:
            breaches.append({"kind": "new_threshold_breach", "metric": m, "baseline": vb, "candidate": vc,
                             "delta": round(vc - vb, 6) if vb is not None else None, "threshold": bound.threshold})

    if candidate.hard_breach:
        breaches.append({"kind": "hard_breach", "metric": "grade", "baseline": baseline.grade,
                         "candidate": candidate.grade, "delta": None})

    verdict = "failed" if breaches else "passed"
    md = render_markdown(verdict, candidate, baseline, breaches, delta, tol, report_url)
    return GateResult(verdict, breaches, md, delta)


def render_markdown(verdict: str, candidate: RunSide, baseline: RunSide, breaches: list[dict[str, Any]],
                    delta: float | None, tol: float, report_url: str | None) -> str:
    icon = "✅" if verdict == "passed" else "❌"
    lines = [
        MARKER,
        f"## {icon} GAUNTLET gate {verdict.upper()}",
        "",
        "| | Baseline | Candidate | Δ |",
        "|---|---|---|---|",
        f"| Readiness | {_fmt(baseline.overall)} ({baseline.grade or '—'}) | {_fmt(candidate.overall)} "
        f"({candidate.grade or '—'}) | {_fmt(delta)} |",
        "",
    ]
    if breaches:
        lines += ["### Breaches", "", "| Metric | Kind | Baseline | Candidate | Δ |", "|---|---|---|---|---|"]
        for b in breaches:
            lines.append(f"| `{b['metric']}` | {b['kind']} | {_fmt(b.get('baseline'))} | "
                         f"{_fmt(b.get('candidate'))} | {_fmt(b.get('delta'))} |")
        lines.append("")
    else:
        lines += [f"No metric crossed its threshold and the score moved within the {tol:g}-point tolerance.", ""]
    lines.append(f"Baseline run `{baseline.run_id}` · candidate run `{candidate.run_id}`")
    if report_url:
        lines.append(f"[Full report]({report_url})")
    return "\n".join(lines) + "\n"
