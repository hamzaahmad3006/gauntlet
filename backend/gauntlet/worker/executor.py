"""Executes one call job end to end (SRS 7 E–K): claim, acquire a concurrency slot, dial, run the caller
session, persist every turn and event, evaluate, account cost, release, and finalise the run when its
last call terminates. Every path — including exceptions — ends with exactly one terminal status and one
reason code on the call (SRS-FR-065)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from gauntlet.caller.adapters.base import TransportError
from gauntlet.caller.adapters.factory import make_transport
from gauntlet.caller.brain import CallerBrain
from gauntlet.caller.session import CallOutcome, CallPlan, CallSession, SessionConfig, turn_payload
from gauntlet.context import ctx
from gauntlet.cost.calculator import RigCounters, SessionShape, estimate_target_cost, rig_cost
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.media.chaos import ChaosParams
from gauntlet.orchestrator.lifecycle import TERMINAL_RUN, finalize_run
from gauntlet.referee.evaluate import PROMPT_VERSION, Evaluator, build_transcript
from gauntlet.referee.transcribe import make_transcriber

log = logging.getLogger("gauntlet.worker")
LEASE_S = 300


async def _set_call(call_id: UUID, **values: Any) -> None:
    async with repo.tx() as c:
        await c.execute(T.calls.update().where(T.calls.c.id == call_id).values(**values))


async def _terminate(call_id: UUID, run_id: UUID, reason: str) -> None:
    await _set_call(call_id, status="errored", reason_code=reason, ended_at=repo.now())
    await ctx().broker.publish(str(run_id), "caller.disconnected",
                               {"call_id": str(call_id), "status": "errored", "reason_code": reason})


async def execute_call(run_id: UUID, call_id: UUID, worker_id: str) -> None:
    c = ctx()
    b = c.broker
    async with repo.tx() as conn:
        claimed = await conn.execute(T.calls.update()
                                     .where(T.calls.c.id == call_id, T.calls.c.status == "pending")
                                     .values(status="dialling", worker_id=worker_id, started_at=repo.now(),
                                             lease_expires_at=repo.now() + timedelta(seconds=LEASE_S)))
        if claimed.rowcount == 0:
            return  # duplicate delivery: another worker owns it (SRS 29 idempotent claims)
        run = repo.d((await conn.execute(sa.select(T.runs).where(T.runs.c.id == run_id))).first())
        call = repo.d((await conn.execute(sa.select(T.calls).where(T.calls.c.id == call_id))).first())
        if run is None or call is None:
            return
        target = repo.d((await conn.execute(sa.select(T.targets).where(T.targets.c.id == run["target_id"]))).first())
        scenario = repo.d((await conn.execute(sa.select(T.scenarios).where(T.scenarios.c.id == call["scenario_id"]))).first())
        persona = repo.d((await conn.execute(sa.select(T.personas).where(T.personas.c.id == call["persona_id"]))).first())
        if run["status"] == "queued":
            await conn.execute(T.runs.update().where(T.runs.c.id == run_id, T.runs.c.status == "queued")
                               .values(status="running", started_at=repo.now()))

    if run["status"] in TERMINAL_RUN or await b.aborted(str(run_id)):
        reason = "budget_exceeded" if await b.r.get(f"run:{run_id}:abort_reason") == "budget" else "run_aborted"
        await _terminate(call_id, run_id, reason)
        await finalize_run(run_id)
        return

    # concurrency slot, honouring the run's limit
    while not await b.acquire_slot(str(run_id), str(call_id), int(run["concurrency_effective"]), LEASE_S):
        if await b.aborted(str(run_id)):
            await _terminate(call_id, run_id, "run_aborted")
            await finalize_run(run_id)
            return
        await asyncio.sleep(0.25)

    abort_event = asyncio.Event()
    current = {"epoch": int(run["current_epoch"]), "params": ChaosParams.from_profile(run["condition_parameters"],
                                                                                        strict=False)}
    got = await b.get_conditions(str(run_id))
    if got:
        current = {"epoch": got[0], "params": ChaosParams.from_profile(got[1], strict=False)}

    async def poll() -> None:
        while not abort_event.is_set():
            await asyncio.sleep(1.0)
            with contextlib.suppress(Exception):
                if await b.aborted(str(run_id)):
                    abort_event.set()
                cond = await b.get_conditions(str(run_id))
                if cond and cond[0] != current["epoch"]:
                    current["epoch"], current["params"] = cond[0], ChaosParams.from_profile(cond[1], strict=False)
                await b.renew_slot(str(run_id), str(call_id), LEASE_S)

    session: CallSession | None = None
    charged = {"usd": 0.0}

    async def budget_ok() -> bool:
        if session is None:
            return True
        total = rig_cost(session.counters, c.pricing)["total_usd"]
        delta, charged["usd"] = total - charged["usd"], total
        spent = await b.add_spend(str(run_id), delta) if delta > 0 else await b.spend(str(run_id))
        if spent >= float(run["spend_cap_usd"]):
            await b.r.set(f"run:{run_id}:abort_reason", "budget", ex=86_400)
            await b.set_abort(str(run_id))
            return False
        return True

    async def publish(kind: str, payload: dict[str, Any]) -> None:
        if kind == "caller.connected":
            await _set_call(call_id, status="in_call")
        await b.publish(str(run_id), kind, payload)

    poller = asyncio.create_task(poll())
    s = c.settings
    outcome: CallOutcome | None = None
    try:
        await b.publish(str(run_id), "caller.started", {"call_id": str(call_id), "scenario_key": call["scenario_key"],
                                                       "persona_key": call["persona_key"]})
        scen = dict(scenario["definition"])
        plan = CallPlan(str(call_id), int(call["seed"]), scen, dict(persona["definition"]), current["params"],
                        list(call["interruption_schedule"] or []), epoch=current["epoch"])
        try:
            transport = make_transport(target, c.key, s.environment, str(call_id))
        except TransportError as e:
            await _terminate(call_id, run_id, e.reason_code)
            return
        brain = CallerBrain(s.groq_api_key, s.groq_base_url, s.caller_model, s.caller_llm_timeout_ms,
                            seed=int(call["seed"]) % 2**31)
        cfg = SessionConfig(turn_timeout_ms=s.turn_timeout_ms, yield_timeout_ms=s.yield_timeout_ms,
                            dead_air_threshold_ms=s.dead_air_threshold_ms, greeting_wait_ms=s.greeting_wait_ms,
                            speech_margin_db=float(target.get("speech_margin_db") or s.speech_margin_db))
        session = CallSession(plan, transport, c.synth, brain, make_transcriber(s.speechmatics_api_key,
                                                                               s.speechmatics_rt_url),
                              cfg, publish, abort_event, budget_ok,
                              lambda: (current["epoch"], current["params"]))
        outcome = await session.run()
        await brain.aclose()
    except Exception as e:  # never let a call leave without a terminal state
        log.exception("call execution failed", extra={"call_id": str(call_id)})
        await _terminate(call_id, run_id, "worker_lost" if isinstance(e, asyncio.CancelledError) else "rig_backpressure")
    finally:
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await poller
        await b.release_slot(str(run_id), str(call_id))

    if outcome is not None:
        await persist(run, call, target, scenario, outcome, charged)
    await b.publish(str(run_id), "run.progress", await progress(run_id))
    await finalize_run(run_id)


async def persist(run: dict[str, Any], call: dict[str, Any], target: dict[str, Any], scenario: dict[str, Any],
                  out: CallOutcome, charged: dict[str, float]) -> None:
    c = ctx()
    run_id, call_id = run["id"], call["id"]
    wav_uri = peaks_uri = None
    flags = set(out.flags)
    if out.wav:
        base = f"workspace/{run['workspace_id']}/runs/{run_id}/calls/{call_id}"
        try:
            wav_uri = await c.storage.put(f"{base}.wav", out.wav, "audio/wav")
            peaks_uri = await c.storage.put(f"{base}.peaks.json", out.peaks or b"{}", "application/json")
        except Exception:
            flags.add("artifact_missing")
    counters = out.counters.as_dict()
    counters.update({"utterances": out.utterances, "cache_hits": out.cache_hits})
    shape = SessionShape(
        agent_audio_seconds=sum(e - s for s, e in out.agent_intervals) / 1e9,
        caller_audio_seconds=sum(e - s for s, e in out.caller_intervals) / 1e9,
        agent_transcript_chars=sum(len(t.agent_text or "") for t in out.turns),
        caller_text_chars=sum(len(t.caller_text or "") for t in out.turns),
    )
    declared = {"unit_prices": target.get("unit_prices")} if target.get("unit_prices") else None
    est = estimate_target_cost(shape, declared) if declared else None
    t0 = out.t0_ns or 0
    status, reason = ("errored", out.reason_code) if out.ended == "errored" else ("scoring", None)
    async with repo.tx() as conn:
        for t in out.turns:
            p = turn_payload(t)
            await conn.execute(T.turns.insert().values(
                call_id=call_id, idx=p["idx"], caller_text=p["caller_text"], agent_text=p["agent_text"],
                agent_confidence=p["agent_confidence"], t_caller_first_voiced_ns=p["t_caller_first_voiced_ns"],
                t_caller_last_sample_ns=p["t_caller_last_sample_ns"], t_agent_first_audio_ns=p["t_agent_first_audio_ns"],
                t_agent_last_audio_ns=p["t_agent_last_audio_ns"], latency_ms=p["latency_ms"],
                raw_latency_ms=p["raw_latency_ms"], censored=p["censored"], premature=p["premature"],
                rig_overhead_ms=p["rig_overhead_ms"], inference_ms=p["inference_ms"], synthesis_ms=p["synthesis_ms"],
                cache_hit=p["cache_hit"], barge_stop_ms=p["barge_stop_ms"], no_yield=p["no_yield"],
                interruption_status=p["interruption_status"], fallback_used=p["fallback_used"], epoch=p["epoch"],
                prompt_tokens=p["prompt_tokens"], completion_tokens=p["completion_tokens"],
                usage_estimated=p["usage_estimated"]))
        if out.events:
            await conn.execute(T.call_events.insert(), [
                {"call_id": call_id, "t_ns": int(e["t_ns"]), "wall_at": repo.now(), "kind": e["kind"][:40],
                 "payload": e["payload"]} for e in out.events])
        m = out.metrics
        await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(
            status=status, reason_code=reason, talkover_ms=m.talkover_ms if m else None,
            dead_air_ratio=m.dead_air_ratio if m else None, duration_ms=out.duration_ms,
            cache_hit_rate=round(100 * out.cache_hits / out.utterances, 3) if out.utterances else None,
            achieved_impairment=out.achieved_impairment,
            interruptions=[i.__dict__ for i in out.interruptions], fallbacks=out.fallbacks, flags=sorted(flags),
            counters=counters, rig_cost_usd=charged["usd"] or rig_cost(out.counters, c.pricing)["total_usd"],
            estimated_target_cost=est,
            intervals={"t0_ns": t0, "caller": [[s - t0, e - t0] for s, e in out.caller_intervals],
                       "agent": [[s - t0, e - t0] for s, e in out.agent_intervals],
                       "windows": [[w.start_ns - t0, w.end_ns - t0] for w in out.windows]},
            referee_engine=out.referee_engine, referee_error=out.referee_error, connect_ms=out.connect_ms,
            audio_uri=wav_uri, waveform_uri=peaks_uri, ended_at=repo.now(),
            expires_at=repo.now() + timedelta(days=c.settings.audio_retention_days)))
    await c.broker.publish(str(run_id), "caller.disconnected", {
        "call_id": str(call_id), "status": status, "reason_code": reason, "duration_ms": out.duration_ms})
    if status == "scoring":
        await evaluate_call(run_id, call_id, scenario["definition"], out)
    spent = await c.broker.spend(str(run_id))
    await c.broker.publish(str(run_id), "spend.updated", {"run_id": str(run_id), "rig_cost_usd": round(spent, 6),
                                                          "cap_usd": float(run["spend_cap_usd"])})


async def evaluate_call(run_id: UUID, call_id: UUID, scenario: dict[str, Any], out: CallOutcome) -> None:
    c = ctx()
    s = c.settings
    ev = Evaluator(s.groq_api_key, s.groq_base_url, s.referee_model)
    turns = await repo.turns_for_call(call_id)
    transcript = build_transcript(turns)
    has_agent_text = any(t.speaker == "agent" and t.text for t in transcript)
    if not ev.enabled or not has_agent_text:
        # No referee transcript or no evaluator: task success cannot be judged. The call's timing is
        # complete; it is recorded as completed and excluded from task-success statistics (SC-04).
        reason = "no_referee_transcript" if not has_agent_text else "no_evaluator"
        await _set_call(call_id, status="completed", reason_code=None)
        await c.broker.publish(str(run_id), "evaluation.completed", {"call_id": str(call_id), "task_success": None,
                                                                     "needs_review": False, "skipped": reason})
        return
    try:
        v = await ev.evaluate(scenario["goal_checklist"], transcript, scenario.get("success_criteria"))
    except Exception as e:
        log.warning("evaluation failed", extra={"call_id": str(call_id), "error": type(e).__name__})
        v = None
    async with repo.tx() as conn:
        if v is None or v.status == "scoring_failed":
            await conn.execute(T.verdicts.insert().values(id=new_id(), call_id=call_id, task_success=None, steps=[],
                                                          status="scoring_failed", model=s.referee_model,
                                                          prompt_version=PROMPT_VERSION))
            # timing is still valid: the call completed; only its task-success judgement failed
            await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(status="completed",
                                                                                     reason_code=None))
        else:
            await conn.execute(T.verdicts.insert().values(
                id=new_id(), call_id=call_id, task_success=v.task_success, steps=v.steps, passes=v.passes,
                needs_review=v.needs_review, agreement=v.agreement, status=v.status, model=v.model,
                prompt_version=PROMPT_VERSION))
            status = "needs_review" if v.needs_review else ("completed" if v.task_success else "failed")
            await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(
                status=status, reason_code=None if status == "completed" else (
                    "goal_not_met" if status == "failed" else "scoring_disagreement")))
            call = repo.d((await conn.execute(sa.select(T.calls.c.counters).where(T.calls.c.id == call_id))).first())
            counters = dict((call or {}).get("counters") or {})
            counters["scorer_prompt_tokens"] = counters.get("scorer_prompt_tokens", 0) + v.prompt_tokens
            counters["scorer_completion_tokens"] = counters.get("scorer_completion_tokens", 0) + v.completion_tokens
            await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(counters=counters))
    if v is not None:
        await c.broker.add_spend(str(run_id), rig_cost(RigCounters(scorer_prompt_tokens=v.prompt_tokens,
                                                                   scorer_completion_tokens=v.completion_tokens),
                                                       c.pricing)["total_usd"])
    await c.broker.publish(str(run_id), "evaluation.completed", {
        "call_id": str(call_id), "task_success": v.task_success if v else None,
        "needs_review": bool(v and v.needs_review), "agreement": v.agreement if v else None})


async def progress(run_id: UUID) -> dict[str, Any]:
    async with repo.tx() as conn:
        rows = (await conn.execute(sa.select(T.calls.c.status, sa.func.count()).where(T.calls.c.run_id == run_id)
                                   .group_by(T.calls.c.status))).all()
    counts = {r[0]: int(r[1]) for r in rows}
    b = ctx().broker
    return {"run_id": str(run_id), "completed": counts.get("completed", 0), "failed": counts.get("failed", 0),
            "needs_review": counts.get("needs_review", 0), "errored": counts.get("errored", 0),
            "total": sum(counts.values()), "active": await b.active(str(run_id)), "peak_concurrency": await b.peak(str(run_id)),
            "queue_depth": counts.get("pending", 0)}
