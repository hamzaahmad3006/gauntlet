"""Targets: register, update, verify ownership, diagnose, promote baseline
(SRS-FR-010..015, -095; API-010..014, API-051)."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from gauntlet.caller.adapters.base import TransportError
from gauntlet.caller.adapters.factory import connection_of, make_transport, validate_connection
from gauntlet.caller.media_session import MediaSession
from gauntlet.caller.transmit import Utterance
from gauntlet.common.crypto import constant_eq, encrypt_json
from gauntlet.context import ctx
from gauntlet.controllers import serialize
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.media.chaos import ChaosParams
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import ApiError, conflict, not_found
from gauntlet.referee.transcribe import make_transcriber
from gauntlet.schemas import TargetCreate, TargetUpdate

UNIT_KEYS = {"llm": ("prompt_price_per_1k_tokens", "completion_price_per_1k_tokens"), "tts": ("price_per_1k_characters",),
             "stt": ("price_per_minute",)}


def _check_prices(prices: dict[str, Any] | None) -> None:
    for comp, spec in (prices or {}).items():
        if comp not in UNIT_KEYS or not isinstance(spec, dict):
            raise ApiError(422, "validation_failed", f"unit_prices.{comp} is not a declarable component",
                           f"/unit_prices/{comp}")
        for k, v in spec.items():
            if k not in UNIT_KEYS[comp] or not isinstance(v, (int, float)) or v < 0:
                raise ApiError(422, "validation_failed", f"unit_prices.{comp}.{k} must be a non-negative number "
                                                         f"(one of {', '.join(UNIT_KEYS[comp])})",
                               f"/unit_prices/{comp}/{k}")


async def _get(p: Principal, target_id: UUID) -> dict[str, Any]:
    row = await repo.one(T.targets, p.workspace_id, target_id)
    if row is None:
        raise not_found("target")
    return row


async def list_targets(p: Principal) -> list[dict[str, Any]]:
    rows = await repo.targets(p.workspace_id)
    out = []
    for r in rows:
        t = serialize.target(r)
        last = await repo.runs(p.workspace_id, r["id"], None, 1, None)
        t["last_run"] = serialize.run(last[0]) if last else None
        if last:
            mets = {m["name"]: m["value"] for m in await repo.run_metrics(last[0]["id"]) if m["epoch"] is None}
            t["last_run"]["headline"] = {k: mets.get(k) for k in ("response_latency_p95", "barge_in_stop_p95",
                                                                   "est_cost_per_successful_session")}
        out.append(t)
    # failures first (PRD 18.1 rule 2)
    order = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, None: 5}
    out.sort(key=lambda t: order.get((t.get("last_run") or {}).get("grade"), 5))
    return out


async def get_target(p: Principal, target_id: UUID) -> dict[str, Any]:
    return serialize.target(await _get(p, target_id))


async def create(p: Principal, body: TargetCreate) -> dict[str, Any]:
    hint = validate_connection(body.adapter, body.connection, ctx().settings.environment)
    _check_prices(body.unit_prices)
    blob, nonce = encrypt_json(ctx().key, body.connection)
    tid = new_id()
    try:
        async with repo.tx() as c:
            await c.execute(T.targets.insert().values(
                id=tid, workspace_id=p.workspace_id, name=body.name, adapter=body.adapter, description=body.description,
                connection_encrypted=blob, connection_nonce=nonce, connection_hint=hint,
                pipeline_declaration=body.pipeline_declaration, unit_prices=body.unit_prices,
                speech_margin_db=body.speech_margin_db))
            await repo.audit(c, p.workspace_id, p.actor, "target.created", f"target:{tid}", {"adapter": body.adapter})
    except IntegrityError:
        raise conflict("name_taken", "a target with this name already exists") from None
    return await get_target(p, tid)


async def update(p: Principal, target_id: UUID, body: TargetUpdate) -> dict[str, Any]:
    row = await _get(p, target_id)
    if body.adapter is not None and body.adapter != row["adapter"]:
        raise conflict("adapter_immutable", "a target's adapter type cannot change after creation")
    values: dict[str, Any] = {}
    for f in ("name", "description", "pipeline_declaration", "speech_margin_db"):
        v = getattr(body, f)
        if v is not None:
            values[f] = v
    if body.unit_prices is not None:
        _check_prices(body.unit_prices)
        values["unit_prices"] = body.unit_prices
    if body.connection is not None:
        values["connection_hint"] = validate_connection(row["adapter"], body.connection, ctx().settings.environment)
        values["connection_encrypted"], values["connection_nonce"] = encrypt_json(ctx().key, body.connection)
        values["verified_at"] = None  # SRS-FR-013: any connection change revokes verification
        values["bundled"] = False
    if values:
        async with repo.tx() as c:
            await c.execute(T.targets.update().where(T.targets.c.id == target_id,
                                                     T.targets.c.workspace_id == p.workspace_id).values(**values))
    return await get_target(p, target_id)


async def verify(p: Principal, target_id: UUID) -> dict[str, Any]:
    """SRS-FR-013 / PRD 22.6: WebSocket targets must echo a fresh nonce; LiveKit targets verify by
    minting a token and joining, which requires the owner's API secret. Deliberately lightweight."""
    row = await _get(p, target_id)
    nonce = secrets.token_hex(16)
    async with repo.tx() as c:
        await c.execute(T.targets.update().where(T.targets.c.id == target_id).values(
            verification_nonce=nonce, verification_nonce_expires_at=repo.now() + timedelta(seconds=300)))
    try:
        transport = make_transport(row, ctx().key, ctx().settings.environment, f"verify-{target_id}", nonce=nonce)
        await asyncio.wait_for(transport.connect(), 25)
        echoed = (getattr(transport, "server_hello", None) or {}).get("nonce")
        await transport.close("verification")
    except (TransportError, asyncio.TimeoutError) as e:
        reason = getattr(e, "reason_code", "connect_failed")
        return {"verified_at": None, "failure_reason": f"{reason}: {e}"[:300]}
    if row["adapter"] == "websocket_pcm" and not (echoed and constant_eq(str(echoed), nonce)):
        return {"verified_at": None, "failure_reason": "the server connected but did not echo the verification nonce "
                                                       "in its hello frame (see docs/ADAPTERS.md)"}
    async with repo.tx() as c:
        await c.execute(T.targets.update().where(T.targets.c.id == target_id).values(
            verified_at=repo.now(), verification_nonce=None))
        await repo.audit(c, p.workspace_id, p.actor, "target.verified", f"target:{target_id}", {})
    return {"verified_at": serialize.jsonable(repo.now())}


async def diagnose(p: Principal, target_id: UUID) -> dict[str, Any]:
    """SRS-FR-014: four independent statuses within 60 s; a connection failure marks the rest not_reached."""
    row = await _get(p, target_id)
    if row["verified_at"] is None:
        raise conflict("target_not_verified", "verify the target before dialling it",
                       verify_url=f"/v1/targets/{target_id}/verify")
    s = ctx().settings
    result = {"connection": {"status": "not_reached"}, "audio_out": {"status": "not_reached"},
              "audio_in": {"status": "not_reached"}, "transcript": {"status": "not_reached"}}
    referee = make_transcriber(s.speechmatics_api_key, s.speechmatics_rt_url)
    try:
        transport = make_transport(row, ctx().key, s.environment, f"diag-{target_id}")
        media = MediaSession(transport, ChaosParams(), 1, record=False, max_seconds=40, on_agent_frame=referee.feed)
        await asyncio.wait_for(media.start(), 25)
    except (TransportError, asyncio.TimeoutError) as e:
        reason = getattr(e, "reason_code", "connect_failed")
        result["connection"] = {"status": "failed", "reason": reason,
                                "hint": "Check the URL, credentials and that the agent is running and reachable."}
        return await _store_diag(target_id, result)
    result["connection"] = {"status": "ok", "connect_ms": transport.connect_ms}
    await referee.start()
    try:
        assert media.tx is not None and media.rx is not None
        await asyncio.sleep(3.0)  # let a greeting play, if any
        utt = media.tx.say(Utterance.from_pcm(
            (await ctx().synth.synthesize("Hello, this is a connectivity check. Can you hear me?",
                                          s.elevenlabs_default_voice_id, 1.0)).pcm))
        sent = await utt.wait(15)
        result["audio_out"] = ({"status": "ok", "frames_sent": media.tx.frames_sent} if sent else
                               {"status": "failed", "hint": "Audio could not be transmitted to the agent."})
        await media.rx.wait_onset(utt.last_voiced_ns or 0, 10.0)
        await asyncio.sleep(2.5)
        heard_ms = media.rx.audio_frames_above_floor * 20
        result["audio_in"] = ({"status": "ok", "heard_ms": heard_ms} if heard_ms >= 500 else
                              {"status": "failed", "heard_ms": heard_ms, "hint": "the agent connected but never spoke"})
        if not referee.enabled and referee.engine == "none":
            result["transcript"] = {"status": "not_configured", "hint": "Set SPEECHMATICS_API_KEY to enable the "
                                                                          "independent referee transcript."}
        else:
            await referee.settle(media.rx.last_t or 0, 3.0)
            ok = any(seg.text for seg in referee.segments)
            result["transcript"] = ({"status": "ok", "sample": referee.segments[0].text[:120]} if ok else
                                    {"status": "failed", "hint": referee.error or "no recognisable speech in the agent's audio"})
    finally:
        await media.stop("diagnostic")
        with contextlib.suppress(Exception):
            await referee.close()
    return await _store_diag(target_id, result)


async def _store_diag(target_id: UUID, result: dict[str, Any]) -> dict[str, Any]:
    result["checked_at"] = serialize.jsonable(repo.now())
    async with repo.tx() as c:
        await c.execute(T.targets.update().where(T.targets.c.id == target_id).values(last_diagnostic=result))
    return result


async def promote_baseline(p: Principal, target_id: UUID, run_id: UUID) -> dict[str, Any]:
    await _get(p, target_id)
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None or run["target_id"] != target_id:
        raise not_found("run")
    if run["status"] != "completed" or "insufficient_sample" in (run["flags"] or []) or run["grade"] is None:
        raise conflict("ungatable_run", "only a completed, graded run can become a baseline")
    async with repo.tx() as c:
        await c.execute(T.targets.update().where(T.targets.c.id == target_id).values(
            baseline_run_id=run_id, baseline_set_at=repo.now(), baseline_set_by=p.actor))
        await c.execute(T.runs.update().where(T.runs.c.id == run_id).values(pinned=True))
        await repo.audit(c, p.workspace_id, p.actor, "baseline.promoted", f"target:{target_id}", {"run_id": str(run_id)})
    return {"baseline_run_id": str(run_id)}


async def connection_for_display(p: Principal, target_id: UUID) -> dict[str, Any]:
    """Never returns secrets: only which fields are set."""
    row = await _get(p, target_id)
    conn = connection_of(row, ctx().key)
    return {k: ("set" if v else "empty") for k, v in conn.items()}


async def ensure_dialable(p: Principal, target_id: UUID) -> dict[str, Any]:
    row = await _get(p, target_id)
    if row["verified_at"] is None:
        raise conflict("target_not_verified", "verify the target before dialling it",
                       verify_url=f"/v1/targets/{target_id}/verify")
    return row


_ = sa
