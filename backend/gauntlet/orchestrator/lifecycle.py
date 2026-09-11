"""ARC-016 run manager — state transitions and run finalisation (SRS 7 J, 8.1).

Finalisation is deterministic: aggregate per-call facts into run metrics, derive the degradation ratio
against the latest clean-profile run on the same target and suite version, compute rig cost from stored
counters, then score against the threshold profile snapshot stored on the run. Recomputing from stored
rows reproduces the result exactly.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from gauntlet.context import ctx
from gauntlet.cost.calculator import RigCounters, rig_cost
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.metrics.aggregate import CallSummary, aggregate, completed_calls, distribution
from gauntlet.metrics.definitions import METRICS
from gauntlet.scoring.normalise import normalise
from gauntlet.scoring.profile import ThresholdProfile
from gauntlet.scoring.score import score

log = logging.getLogger("gauntlet.lifecycle")
TERMINAL_RUN = {"completed", "aborted", "aborted_budget", "failed"}
TERMINAL_CALL = {"completed", "failed", "needs_review", "errored"}


def summarise_call(call: dict[str, Any], turns: list[dict[str, Any]], verdict: dict[str, Any] | None) -> CallSummary:
    caller_turns = [t for t in turns if t["idx"] >= 1]
    lat = [t["latency_ms"] for t in caller_turns if t["latency_ms"] is not None and not t["censored"]]
    first = next((t["latency_ms"] for t in caller_turns if t["idx"] == 1), None)
    intr = call.get("interruptions") or []
    applied = [i for i in intr if i.get("status") == "applied"]
    counters = call.get("counters") or {}
    verdict_scored = verdict is not None and verdict["status"] != "scoring_failed"
    return CallSummary(
        status=call["status"],
        attempt=call["attempt"],
        turn_latencies=lat,
        first_turn_latency=first,
        barge_stops=[float(i["barge_stop_ms"]) for i in applied if i.get("barge_stop_ms") is not None],
        yields=sum(1 for i in applied if not i.get("no_yield")),
        applicable_interruptions=len(applied),
        talkover_ms=call.get("talkover_ms"),
        dead_air_ratio=call.get("dead_air_ratio"),
        rig_overheads=[t["rig_overhead_ms"] for t in caller_turns if t["rig_overhead_ms"] is not None],
        turns=len(caller_turns),
        fallback_turns=sum(1 for t in caller_turns if t["fallback_used"]),
        premature_turns=sum(1 for t in caller_turns if t["premature"]),
        cache_hits=int(counters.get("cache_hits", 0)),
        utterances=int(counters.get("utterances", 0)),
        task_success=verdict.get("task_success") if verdict else None,
        scored=verdict_scored,
        needs_review=bool(verdict and verdict["needs_review"]),
        est_target_cost_usd=(call.get("estimated_target_cost") or {}).get("estimated_usd"),
    )


def epoch_breakdown(turns: list[dict[str, Any]], calls_by_id: dict[UUID, dict[str, Any]]) -> list[dict[str, Any]]:
    """SRS-FR-038: metrics separable by condition epoch."""
    epochs: dict[int, list[float]] = {}
    for t in turns:
        if t["idx"] < 1 or t["latency_ms"] is None or t["censored"]:
            continue
        if calls_by_id.get(t["call_id"], {}).get("status") == "errored":
            continue
        epochs.setdefault(int(t["epoch"]), []).append(float(t["latency_ms"]))
    out = []
    for e in sorted(epochs):
        dist = distribution("response_latency", "ms", epochs[e])
        out.append({"epoch": e, "n": dist.n, "p50": dist.p50, "p95": dist.p95, "flags": dist.flags})
    return out


async def finalize_run(run_id: UUID) -> dict[str, Any] | None:
    c = ctx()
    async with repo.tx() as conn:
        run = repo.d((await conn.execute(sa.select(T.runs).where(T.runs.c.id == run_id))).first())
    if run is None or run["status"] in TERMINAL_RUN:
        return run
    ws = run["workspace_id"]
    calls = await repo.calls_for_run(ws, run_id)
    if any(cl["status"] not in TERMINAL_CALL for cl in calls):
        return run  # not yet
    turns = await repo.turns_for_run(run_id)
    verdicts = await repo.verdicts_for_run(run_id)
    by_call: dict[UUID, list[dict[str, Any]]] = {}
    for t in turns:
        by_call.setdefault(t["call_id"], []).append(t)
    summaries = [summarise_call(cl, by_call.get(cl["id"], []), verdicts.get(cl["id"])) for cl in calls]
    agg = aggregate(summaries)
    metrics = {k: v.value for k, v in agg.items()}

    flags: set[str] = set(run.get("flags") or [])
    # MET-15: degradation against the latest clean run on the same target and suite version
    if run["condition_profile_key"] != "clean":
        clean = await repo.latest_clean_run(ws, run["target_id"], run["suite_version_hash"],
                                            run["definitions_version"], run_id)
        if clean is not None:
            clean_p95 = next((m["value"] for m in await repo.run_metrics(clean["id"])
                              if m["name"] == "response_latency_p95" and m["epoch"] is None), None)
            if clean_p95 and metrics.get("response_latency_p95"):
                metrics["degradation_ratio"] = round(metrics["response_latency_p95"] / clean_p95, 4)
                flags.add(f"degradation_reference:{clean['id']}")

    counters = RigCounters()
    for cl in calls:
        cc = {k: v for k, v in (cl.get("counters") or {}).items() if k in RigCounters.__dataclass_fields__}
        counters.add(RigCounters(**cc))
    cost = rig_cost(counters, c.pricing)
    flags.update(cost["flags"])
    est_total = sum(s.est_target_cost_usd for s in summaries if s.est_target_cost_usd is not None) or None

    profile = ThresholdProfile.from_document(run["threshold_document"])
    n_completed = completed_calls(summaries)
    result = score(metrics, profile, n_completed)
    flags.update(result.flags)
    if agg.get("response_latency_p95") and "low_sample" in agg["response_latency_p95"].flags:
        flags.add("low_sample")
    if any("referee_unavailable" in (cl.get("flags") or []) for cl in calls):
        flags.add("referee_unavailable")

    aborted = await c.broker.aborted(str(run_id))
    reason = await c.broker.r.get(f"run:{run_id}:abort_reason") if aborted else None
    if aborted:
        status = "aborted_budget" if reason == "budget" else "aborted"
    elif calls and all(cl["status"] == "errored" and cl["reason_code"] in
                       ("connect_failed", "auth_failed", "no_remote_audio", "protocol_error") for cl in calls):
        status = "failed"
    else:
        status = "completed"

    peak = await c.broker.peak(str(run_id))
    score_doc = result.as_dict()
    score_doc["epochs"] = epoch_breakdown(turns, {cl["id"]: cl for cl in calls})
    score_doc["completed_calls"] = n_completed
    score_doc["metric_details"] = {k: v.as_dict() for k, v in agg.items()}
    async with repo.tx() as conn:
        await conn.execute(T.run_metrics.delete().where(T.run_metrics.c.run_id == run_id))
        names = set(agg) | ({"degradation_ratio"} if "degradation_ratio" in metrics else set())
        for name in sorted(names):
            mv = agg.get(name)
            value = metrics.get(name)
            bound = profile.bounds.get(name)
            await conn.execute(T.run_metrics.insert().values(
                run_id=run_id, name=name, value=value, n=mv.n if mv else 1,
                unit=(mv.unit if mv else METRICS.get(name).unit if name in METRICS else ""),
                normalised=float(normalise(value, bound)) if (bound and value is not None) else None,
                flags=(mv.flags if mv else []), epoch=None))
        await conn.execute(T.runs.update().where(T.runs.c.id == run_id).values(
            status=status, flags=sorted(flags), score=score_doc, grade=result.grade, overall=result.overall,
            rig_cost_usd=cost["total_usd"], rig_cost=cost, estimated_target_cost_usd=est_total,
            concurrency_peak=peak, ended_at=repo.now()))
    await c.broker.publish(str(run_id), "run.completed" if status == "completed" else "run.failed",
                           {"run_id": str(run_id), "status": status, "grade": result.grade, "overall": result.overall,
                            "flags": sorted(flags), "suppressed_reason": result.suppressed_reason})
    await c.broker.retain_events(str(run_id), 3600)
    log.info("run finalised", extra={"run_id": str(run_id), "status": status, "grade": result.grade})
    return await repo.run_row(ws, run_id)
