"""Runs: create, estimate, list, summary, abort, mid-run condition injection, live events
(SRS-FR-030..039; API-030..036)."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from gauntlet.caller.interrupts import interruptions_for, schedule
from gauntlet.common import seeds
from gauntlet.context import ctx
from gauntlet.controllers import serialize
from gauntlet.controllers.targets_controller import ensure_dialable
from gauntlet.cost.calculator import RigCounters, rig_cost
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.media.chaos import ChaosParams, ConditionError
from gauntlet.metrics import disclosures
from gauntlet.metrics.definitions import DEFINITIONS_VERSION
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import ApiError, conflict, invalid, not_found
from gauntlet.schemas import ConditionChange, RunCreate

TERMINAL = {"completed", "aborted", "aborted_budget", "failed"}


async def _plan(p: Principal, body: RunCreate) -> dict[str, Any]:
    s = ctx().settings
    suite = await repo.one(T.suites, p.workspace_id, body.suite_id)
    if suite is None:
        raise not_found("suite")
    cond = await repo.condition_profile(p.workspace_id, body.condition_profile_key)
    if cond is None:
        raise invalid(f"unknown condition profile '{body.condition_profile_key}'", "/condition_profile_key")
    try:
        params = ChaosParams.from_profile(cond["parameters"], strict=True)
    except ConditionError as e:
        raise invalid(str(e), f"/parameters/{e.parameter}") from None
    thr = await repo.threshold_profile(p.workspace_id, body.threshold_profile_key)
    if thr is None:
        raise invalid(f"unknown threshold profile '{body.threshold_profile_key}'", "/threshold_profile_key")
    scen_rows, pers_rows = await repo.suite_children(suite["id"])
    if body.scenario_keys:
        scen_rows = [r for r in scen_rows if r["key"] in set(body.scenario_keys)]
    if body.persona_keys:
        pers_rows = [r for r in pers_rows if r["key"] in set(body.persona_keys)]
    if not scen_rows or not pers_rows:
        raise invalid("the scenario/persona selection is empty", "/scenario_keys")
    total = len(scen_rows) * len(pers_rows) * body.repeats
    if total > s.max_calls_per_run:
        raise invalid(f"{total} calls exceeds MAX_CALLS_PER_RUN ({s.max_calls_per_run})", "/repeats")
    effective = min(body.concurrency, s.max_concurrent_calls)
    return {"suite": suite, "cond": cond, "params": params, "thr": thr, "scenarios": scen_rows, "personas": pers_rows,
            "total": total, "effective": effective, "clamped": effective != body.concurrency}


def _estimate(plan: dict[str, Any], body: RunCreate) -> dict[str, Any]:
    """SRS-FR-031, docs/COST_MODEL.md: expected turns x per-turn usage x configured prices."""
    c = ctx()
    s = c.settings
    avg_turns = sum(min(int(r["max_turns"]), 8) for r in plan["scenarios"]) / len(plan["scenarios"])
    call_s = sum(min(int(r["max_duration_s"]), avg_turns * 7.0) for r in plan["scenarios"]) / len(plan["scenarios"])
    waves = math.ceil(plan["total"] / plan["effective"])
    per_call = RigCounters(
        llm_prompt_tokens=int(avg_turns * 700) if s.groq_api_key else 0,
        llm_completion_tokens=int(avg_turns * 40) if s.groq_api_key else 0,
        tts_characters=int(avg_turns * 60) if s.elevenlabs_api_key else 0,
        stt_audio_seconds=call_s * 0.5 if s.speechmatics_api_key else 0,
        scorer_prompt_tokens=2 * 1500 if (s.groq_api_key and s.speechmatics_api_key) else 0,
        scorer_completion_tokens=2 * 200 if (s.groq_api_key and s.speechmatics_api_key) else 0,
    )
    one = rig_cost(per_call, c.pricing)
    assumptions = [f"~{avg_turns:.1f} caller turns per call, ~{call_s:.0f} s per call",
                   "synthesis cost assumes no cache hits (an upper bound on repeat runs)",
                   "wall-clock = ceil(calls / concurrency) x mean call duration + 20 s setup"]
    if one["flags"]:
        assumptions.append("pricing_not_configured: config/pricing.yaml holds zero placeholders")
    for prov, on in s.providers.items():
        if prov in ("caller_llm", "caller_tts", "referee_stt") and not on:
            assumptions.append(f"{prov} not configured — its documented fallback is used and costs nothing")
    return {"calls": plan["total"], "concurrency_effective": plan["effective"],
            "estimated_duration_s": round(waves * call_s + 20), "estimated_rig_cost_usd": round(one["total_usd"] * plan["total"], 4),
            "assumptions": assumptions}


async def estimate(p: Principal, body: RunCreate) -> dict[str, Any]:
    await ensure_dialable(p, body.target_id)
    return _estimate(await _plan(p, body), body)


async def create(p: Principal, body: RunCreate, idempotency_key: str | None) -> dict[str, Any]:
    c = ctx()
    s = c.settings
    if idempotency_key:
        async with repo.tx() as conn:
            existing = repo.d((await conn.execute(sa.select(T.runs).where(
                T.runs.c.workspace_id == p.workspace_id, T.runs.c.idempotency_key == idempotency_key))).first())
        if existing:
            return {"run": serialize.run(existing), "idempotent_replay": True}
    target = await ensure_dialable(p, body.target_id)
    plan = await _plan(p, body)
    ws = await repo.workspace(p.workspace_id)
    if await repo.active_run_count(p.workspace_id) >= int(ws["max_concurrent_runs"]):
        raise ApiError(429, "run_limit_exceeded", "This workspace already has the maximum number of runs in flight.",
                       headers={"Retry-After": "60"})
    if await repo.trailing_spend(p.workspace_id) >= float(ws["daily_spend_cap_usd"]):
        raise ApiError(429, "spend_cap_exceeded", "The workspace's daily spend ceiling has been reached.",
                       headers={"Retry-After": "3600"})
    seed = body.seed if body.seed is not None else seeds.new_run_seed()
    run_id = new_id()
    params: ChaosParams = plan["params"]
    cap = body.spend_cap_usd if body.spend_cap_usd is not None else s.default_run_spend_cap_usd
    flags = ["concurrency_clamped"] if plan["clamped"] else []
    call_rows = []
    for sc in plan["scenarios"]:
        for pe in plan["personas"]:
            for rep in range(body.repeats):
                cs = seeds.call_seed(seed, sc["key"], pe["key"], rep)
                n_int = interruptions_for(pe["definition"], params.interruptions_per_call)
                call_rows.append({
                    "id": new_id(), "run_id": run_id, "scenario_id": sc["id"], "persona_id": pe["id"],
                    "scenario_key": sc["key"], "persona_key": pe["key"], "coverage_tag": sc["coverage_tag"],
                    "repeat_index": rep, "seed": cs,
                    "interruption_schedule": schedule(cs, n_int, params.offset_range_ms, int(sc["max_turns"])),
                    "status": "pending", "fallbacks": {}, "flags": []})
    async with repo.tx() as conn:
        await conn.execute(T.runs.insert().values(
            id=run_id, workspace_id=p.workspace_id, target_id=target["id"], suite_id=plan["suite"]["id"],
            suite_version_hash=plan["suite"]["version_hash"], condition_profile_key=plan["cond"]["key"],
            condition_parameters=plan["cond"]["parameters"], threshold_profile_key=plan["thr"]["key"],
            threshold_version_hash=plan["thr"]["version_hash"], threshold_document=plan["thr"]["document"],
            definitions_version=DEFINITIONS_VERSION, seed=seed, concurrency_requested=body.concurrency,
            concurrency_effective=plan["effective"], repeats=body.repeats, total_calls=len(call_rows),
            status="queued", flags=flags, spend_cap_usd=cap, label=body.label, current_epoch=0,
            epochs=[{"epoch": 0, "parameters": plan["cond"]["parameters"], "profile": plan["cond"]["key"],
                     "effective_at": serialize.jsonable(repo.now())}],
            providers=s.providers, created_by=p.actor, idempotency_key=idempotency_key))
        await conn.execute(T.calls.insert(), call_rows)
        await repo.audit(conn, p.workspace_id, p.actor, "run.created", f"run:{run_id}",
                         {"calls": len(call_rows), "seed": str(seed)})
        await c.broker.set_conditions(str(run_id), 0, plan["cond"]["parameters"])
        for row in call_rows:  # enqueue inside the transaction: a failure rolls the run back (SRS 7 D)
            await c.broker.enqueue(str(run_id), str(row["id"]))
    await c.broker.publish(str(run_id), "run.started", {"run_id": str(run_id), "total_calls": len(call_rows),
                                                        "concurrency": plan["effective"], "seed": str(seed)})
    run = await repo.run_row(p.workspace_id, run_id)
    return {"run": serialize.run(run), "enqueued": len(call_rows)}


async def list_runs(p: Principal, target_id: UUID | None, status: str | None, limit: int,
                    cursor: str | None) -> dict[str, Any]:
    cur = None
    if cursor:
        try:
            cur = datetime.fromisoformat(cursor)
        except ValueError:
            raise ApiError(400, "invalid_cursor", "the cursor is not valid") from None
    rows = await repo.runs(p.workspace_id, target_id, status, limit, cur)
    names = {t["id"]: t["name"] for t in await repo.targets(p.workspace_id)}
    items = []
    for r in rows:
        x = serialize.run(r)
        x["target_name"] = names.get(r["target_id"])
        items.append(x)
    nxt = serialize.jsonable(rows[-1]["created_at"]) if len(rows) == limit else None
    return {"items": items, "next_cursor": nxt}


async def summary(p: Principal, run_id: UUID) -> dict[str, Any]:
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None:
        raise not_found("run")
    target = await repo.one(T.targets, p.workspace_id, run["target_id"])
    calls = await repo.calls_for_run(p.workspace_id, run_id)
    metrics = await repo.run_metrics(run_id)
    b = ctx().broker
    live = {}
    if run["status"] not in TERMINAL:
        live = {"active": await b.active(str(run_id)), "peak": await b.peak(str(run_id)),
                "spend_usd": await b.spend(str(run_id))}
    order = {"errored": 0, "failed": 1, "needs_review": 2, "completed": 3}
    calls_out = sorted((serialize.call(cl) for cl in calls), key=lambda x: order.get(x["status"], 4))
    cal = ctx().calibration
    return {
        "run": serialize.run(run),
        "score": run.get("score"),
        "target": {"id": str(target["id"]), "name": target["name"], "adapter": target["adapter"],
                   "bundled": target["bundled"], "baseline_run_id": serialize.jsonable(target["baseline_run_id"]),
                   "cost_model_declared": bool(target.get("unit_prices"))} if target else None,
        "metrics": serialize.jsonable(metrics),
        "calls": calls_out,
        "threshold_document": run["threshold_document"],
        "live": live,
        "calibration": {"bound_ms": cal.get("bound_ms"), "scope": disclosures.CALIBRATION_SCOPE} if cal else None,
        "disclosure": disclosures.IMPAIRMENT_DISCLOSURE,
        "disclosures": disclosures.ALL,
    }


async def abort(p: Principal, run_id: UUID) -> dict[str, Any]:
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None:
        raise not_found("run")
    if run["status"] in TERMINAL:
        raise conflict("run_terminal", f"run is already {run['status']}")
    b = ctx().broker
    await b.set_abort(str(run_id))
    async with repo.tx() as conn:
        await conn.execute(T.calls.update().where(T.calls.c.run_id == run_id, T.calls.c.status == "pending")
                           .values(status="errored", reason_code="run_aborted", ended_at=repo.now()))
        await repo.audit(conn, p.workspace_id, p.actor, "run.aborted", f"run:{run_id}", {})
    from gauntlet.orchestrator.lifecycle import finalize_run

    asyncio.get_running_loop().create_task(_finalize_soon(run_id))
    _ = finalize_run
    return {"status": "aborting"}


async def _finalize_soon(run_id: UUID) -> None:
    from gauntlet.orchestrator.lifecycle import finalize_run

    for _ in range(15):
        await asyncio.sleep(1.0)
        r = await finalize_run(run_id)
        if r and r["status"] in TERMINAL:
            return


async def inject_conditions(p: Principal, run_id: UUID, body: ConditionChange) -> dict[str, Any]:
    """SRS-FR-038: calls adopt the change at their next turn boundary; epochs keep metrics separable."""
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None:
        raise not_found("run")
    if run["status"] not in ("queued", "running"):
        raise conflict("run_not_running", "conditions can only change while a run is in flight")
    params_doc = body.parameters
    if body.profile_key:
        prof = await repo.condition_profile(p.workspace_id, body.profile_key)
        if prof is None:
            raise invalid(f"unknown condition profile '{body.profile_key}'", "/profile_key")
        params_doc = prof["parameters"]
    try:
        ChaosParams.from_profile(params_doc, strict=True)
    except ConditionError as e:
        raise invalid(str(e), f"/parameters/{e.parameter}") from None
    epoch = int(run["current_epoch"]) + 1
    effective_at = serialize.jsonable(repo.now())
    epochs = list(run["epochs"] or []) + [{"epoch": epoch, "parameters": params_doc, "profile": body.profile_key,
                                           "effective_at": effective_at}]
    async with repo.tx() as conn:
        await conn.execute(T.runs.update().where(T.runs.c.id == run_id).values(current_epoch=epoch, epochs=epochs))
        await repo.audit(conn, p.workspace_id, p.actor, "run.conditions_changed", f"run:{run_id}", {"epoch": epoch})
    await ctx().broker.set_conditions(str(run_id), epoch, params_doc)
    await ctx().broker.publish(str(run_id), "chaos.changed", {"run_id": str(run_id), "epoch": epoch,
                                                              "parameters": params_doc, "profile": body.profile_key,
                                                              "effective_at": effective_at})
    return {"epoch": epoch, "effective_at": effective_at}


async def event_stream(p: Principal, run_id: UUID, last_event_id: str | None) -> AsyncIterator[bytes]:
    """SRS-FR-037: server-sent events with replay from Last-Event-ID and a 15 s heartbeat."""
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None:
        raise not_found("run")
    return _sse(run_id, last_event_id)


async def _sse(run_id: UUID, last_event_id: str | None) -> AsyncIterator[bytes]:
    b = ctx().broker
    last = last_event_id or "0"
    yield b"retry: 2000\n\n"
    terminal_seen_at: float | None = None
    loop = asyncio.get_running_loop()
    while True:
        try:
            events = await b.read_events(str(run_id), last, block_ms=15_000)
        except Exception:
            yield b": broker-unavailable\n\n"
            await asyncio.sleep(2)
            continue
        if not events:
            yield b": heartbeat\n\n"
        for eid, kind, seq, payload in events:
            last = eid
            data = json.dumps({"seq": seq, "kind": kind, **payload}, default=str)
            yield f"id: {eid}\nevent: {kind}\ndata: {data}\n\n".encode()
            if kind in ("run.completed", "run.failed"):
                terminal_seen_at = loop.time()
        if terminal_seen_at is not None and loop.time() - terminal_seen_at > 5:
            return
