"""ARC-045 report generator (SRS-FR-110..112, SRS 21.8).

A report carries methodology, suite hash, seed, threshold profile and version, full condition parameters,
every metric with its evidence label, the calibration bound with its scope, and the mandatory
limitations. The limitations section is always rendered and cannot be collapsed. Evidence labels:
MEASURED (produced by this run), THRESHOLD (policy), ESTIMATED (model over declared prices).
"""

from __future__ import annotations

import html
from typing import Any

from gauntlet.metrics import disclosures
from gauntlet.metrics.definitions import METRICS

LIMITATIONS = [
    disclosures.IMPAIRMENT_DISCLOSURE,
    disclosures.CALIBRATION_SCOPE,
    disclosures.TASK_SUCCESS_IS_INFERENCE,
    disclosures.REPRODUCIBILITY,
    "Time-to-first-token is not measurable in black-box mode; GAUNTLET measures time to first audio.",
    "Dead air counts agent-side silence only; the caller's own think time is excluded by design.",
    "Energy-based voice activity detection can detect late or fail on agents with continuous background audio.",
]


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:,.3f}".rstrip("0").rstrip(".")
    else:
        s = str(v)
    return f"{s} {unit}".strip() if unit and unit not in ("%",) else (s + unit if unit == "%" else s)


def build(run: dict[str, Any], metrics: list[dict[str, Any]], target_name: str, suite_name: str,
          calibration: dict[str, Any] | None, public: bool = False, calls: list[dict[str, Any]] | None = None,
          declaration: dict[str, Any] | None = None) -> dict[str, Any]:
    from gauntlet.referee.transcribe import independence

    score = run.get("score") or {}
    profile = run.get("threshold_document") or {}
    bounds = profile.get("metrics") or {}
    rows = []
    for m in metrics:
        if m.get("epoch") is not None:
            continue
        d = METRICS.get(m["name"])
        b = bounds.get(m["name"])
        status = None
        if b and m["value"] is not None:
            ok = m["value"] <= b["threshold"] if b["direction"] == "lower_is_better" else m["value"] >= b["threshold"]
            status = "pass" if ok else "breach"
        label = "ESTIMATED" if m["name"].startswith("est_") else "MEASURED"
        rows.append({"name": m["name"], "met_id": d.met_id if d else "", "label": d.label if d else m["name"],
                     "value": m["value"], "unit": m["unit"], "n": m["n"], "flags": m.get("flags") or [],
                     "threshold": b["threshold"] if b else None, "ideal": b["ideal"] if b else None,
                     "direction": b["direction"] if b else None, "status": status, "evidence": label,
                     "definition": d.definition if d else ""})
    rows.sort(key=lambda r: (r["status"] != "breach", r["met_id"] or "~", r["name"]))
    outcome: dict[str, int] = {}
    for c in calls or []:
        outcome[c["status"]] = outcome.get(c["status"], 0) + 1
    rig = run.get("rig_cost") or {}
    return {
        "run_id": str(run["id"]),
        "label": run.get("label"),
        "status": run["status"],
        "grade": run.get("grade"),
        "overall": run.get("overall"),
        "suppressed_reason": score.get("suppressed_reason"),
        "caps": score.get("caps") or [],
        # public view exposes no identifier other than this run's own (SRS-FR-111)
        "flags": [f for f in (run.get("flags") or []) if not (public and ":" in f)],
        "subscores": score.get("subscores") or [],
        "epochs": score.get("epochs") or [],
        "metrics": rows,
        "target": target_name,
        "suite": {"name": suite_name, "version_hash": run["suite_version_hash"]},
        "seed": str(run["seed"]),
        "conditions": {"profile": run["condition_profile_key"], "parameters": run["condition_parameters"],
                       "epochs": run.get("epochs") or []},
        "thresholds": {"profile": run["threshold_profile_key"], "version_hash": run["threshold_version_hash"]},
        "definitions_version": run["definitions_version"],
        "concurrency": {"requested": run["concurrency_requested"], "effective": run["concurrency_effective"],
                        "peak_measured": run.get("concurrency_peak")},
        "calls": {"total": run.get("total_calls"), "outcomes": outcome},
        "cost": {"rig_usd": run.get("rig_cost_usd"), "rig_breakdown": rig.get("breakdown"),
                 "rig_label": "MEASURED from provider-returned counters x configured prices",
                 "pricing_flags": rig.get("flags") or [],
                 "estimated_target_usd": None if public else run.get("estimated_target_cost_usd"),
                 "estimated_label": disclosures.TARGET_COST_ESTIMATED},
        "calibration": {"bound_ms": calibration.get("bound_ms"), "n": calibration.get("n"),
                        "git_sha": calibration.get("git_sha"), "run_at": calibration.get("run_at"),
                        "environment": calibration.get("environment"), "scope": disclosures.CALIBRATION_SCOPE}
        if calibration else None,
        "methodology": {
            "measured_controlled": "One caller process owns both audio directions on one clock; timings are acoustic, "
                                   "from received audio, with sub-frame interpolation.",
            "referee": disclosures.REFEREE_INDEPENDENCE,
            "scoring": "Deterministic piecewise-linear normalisation against the threshold profile; no model assigns "
                       "the score.",
        },
        "independence": independence({c.get("referee_engine") or "" for c in (calls or [])}, declaration),
        "limitations": LIMITATIONS,
        "disclosure": disclosures.IMPAIRMENT_DISCLOSURE,
        "created_at": str(run.get("created_at")),
        "ended_at": str(run.get("ended_at")),
    }


def to_markdown(r: dict[str, Any]) -> str:
    grade = r["grade"] or "—"
    head = f"# GAUNTLET report — {r['target']}\n\n"
    head += f"**Run** `{r['run_id']}` · status **{r['status']}** · grade **{grade}**"
    head += f" · score **{_fmt(r['overall'])}**\n\n" if r["overall"] is not None else "\n\n"
    if r["suppressed_reason"]:
        head += f"> Grade not emitted: {r['suppressed_reason']}\n\n"
    for cap in r["caps"]:
        head += f"> Capped at F: {cap}\n\n"
    out = [head, "## Metrics\n", "| Metric | Value | Threshold | Status | n | Evidence |", "|---|---|---|---|---|---|"]
    for m in r["metrics"]:
        out.append(f"| {m['met_id']} {m['label']} | {_fmt(m['value'], m['unit'])} | "
                   f"{_fmt(m['threshold'], m['unit']) if m['threshold'] is not None else '—'} (THRESHOLD) | "
                   f"{m['status'] or '—'} | {m['n']} | {m['evidence']} |")
    out += ["", "## Sub-scores\n", "| Sub-score | Score | Weight | Effective weight |", "|---|---|---|---|"]
    for s in r["subscores"]:
        out.append(f"| {s['id']} {s['name']} | {_fmt(s['score']) if s['available'] else 'unavailable'} | "
                   f"{s['weight']} | {s['effective_weight']} |")
    c = r["conditions"]
    out += ["", "## Configuration\n",
            f"- Suite: {r['suite']['name']} `{r['suite']['version_hash'][:16]}…`",
            f"- Seed: `{r['seed']}`",
            f"- Conditions: `{c['profile']}` {c['parameters'] or '{}'}",
            f"- Thresholds: `{r['thresholds']['profile']}` `{r['thresholds']['version_hash'][:16]}…`",
            f"- Concurrency: requested {r['concurrency']['requested']}, measured peak "
            f"{_fmt(r['concurrency']['peak_measured'])}",
            f"- Rig cost (MEASURED): {_fmt(r['cost']['rig_usd'])} USD {' '.join(r['cost']['pricing_flags'])}"]
    if r["calibration"]:
        cal = r["calibration"]
        out += ["", "## Calibration\n",
                f"Measurement error bound **{_fmt(cal['bound_ms'])} ms** over {cal['n']} loopback repetitions "
                f"(commit `{(cal['git_sha'] or '')[:8]}`, {cal['environment']}). {cal['scope']}"]
    out += ["", "## Limitations\n"] + [f"- {x}" for x in r["limitations"]]
    return "\n".join(out) + "\n"


def to_html(r: dict[str, Any]) -> str:
    e = html.escape
    rows = "".join(
        f"<tr class='{m['status'] or ''}'><td>{e(m['met_id'])} {e(m['label'])}</td><td class=n>{e(_fmt(m['value'], m['unit']))}</td>"
        f"<td class=n>{e(_fmt(m['threshold'], m['unit'])) if m['threshold'] is not None else '—'}</td>"
        f"<td>{e(m['status'] or '—')}</td><td class=n>{m['n']}</td><td><span class=lbl>{e(m['evidence'])}</span></td></tr>"
        for m in r["metrics"])
    subs = "".join(f"<tr><td>{e(s['id'])} {e(s['name'])}</td><td class=n>"
                   f"{e(_fmt(s['score'])) if s['available'] else 'unavailable'}</td><td class=n>{s['weight']}</td></tr>"
                   for s in r["subscores"])
    lim = "".join(f"<li>{e(x)}</li>" for x in r["limitations"])
    grade = e(r["grade"] or "—")
    verdict = (f"<p class=warn>Grade not emitted: {e(r['suppressed_reason'])}</p>" if r["suppressed_reason"] else "")
    verdict += "".join(f"<p class=warn>Capped at F: {e(c)}</p>" for c in r["caps"])
    cal = r["calibration"]
    cal_html = (f"<p>Measurement error bound <b>{e(_fmt(cal['bound_ms']))} ms</b> over {cal['n']} loopback repetitions "
                f"(commit <code>{e((cal['git_sha'] or '')[:8])}</code>). {e(cal['scope'])}</p>") if cal else \
        "<p>No calibration artefact available.</p>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>GAUNTLET report · {e(r['target'])}</title><style>
body{{font:14px/1.5 ui-sans-serif,system-ui,sans-serif;margin:0;background:#0b0d10;color:#e6e8eb}}
main{{max-width:980px;margin:0 auto;padding:24px 16px}} h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:15px;margin:28px 0 8px;color:#9aa4b2;text-transform:uppercase;letter-spacing:.06em}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}} td,th{{padding:6px 8px;border-bottom:1px solid #20252c;text-align:left}}
td.n{{text-align:right}} tr.breach td{{color:#ff8a80}} .grade{{font-size:40px;font-weight:700}} .lbl{{font-size:11px;border:1px solid #3a4250;border-radius:4px;padding:1px 5px;color:#9aa4b2}}
.warn{{color:#ffcc80}} code{{color:#b3c7ff}} .box{{overflow-x:auto}} .lim{{border:1px solid #3a4250;border-radius:8px;padding:8px 16px;background:#11151a}}
@media (prefers-color-scheme: light){{body{{background:#fafafa;color:#111}} td,th{{border-color:#e5e7eb}} .lim{{background:#fff;border-color:#e5e7eb}} code{{color:#1d4ed8}}}}
</style></head><body><main>
<h1>GAUNTLET report — {e(r['target'])}</h1><div>Run <code>{e(r['run_id'])}</code> · {e(r['status'])}</div>
<div class=grade>{grade} <small>{e(_fmt(r['overall']))}</small></div>{verdict}
<h2>Metrics</h2><div class=box><table><tr><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th><th>n</th><th>Evidence</th></tr>{rows}</table></div>
<h2>Sub-scores</h2><div class=box><table><tr><th>Sub-score</th><th>Score</th><th>Weight</th></tr>{subs}</table></div>
<h2>Configuration</h2><p>Suite {e(r['suite']['name'])} <code>{e(r['suite']['version_hash'][:16])}…</code> · seed <code>{e(r['seed'])}</code>
· conditions <code>{e(r['conditions']['profile'])}</code> · thresholds <code>{e(r['thresholds']['profile'])}</code>
· concurrency requested {r['concurrency']['requested']}, measured peak {e(_fmt(r['concurrency']['peak_measured']))}
· rig cost {e(_fmt(r['cost']['rig_usd']))} USD (MEASURED) {e(' '.join(r['cost']['pricing_flags']))}</p>
<h2>Calibration</h2>{cal_html}
{('<p class=warn>' + e(r['independence']['warning']) + '</p>') if (r.get('independence') or {}).get('warning') else ''}
<h2>Limitations</h2><div class=lim><ul>{lim}</ul></div>
</main></body></html>"""
