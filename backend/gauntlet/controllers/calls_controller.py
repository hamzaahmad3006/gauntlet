"""Call detail: turns, events, transcript, verdict, artefacts (SRS-FR-060..073; API-040)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from gauntlet.context import ctx
from gauntlet.controllers import serialize
from gauntlet.db import repo
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import not_found


async def _call(p: Principal, call_id: UUID) -> dict[str, Any]:
    row = await repo.call_row(p.workspace_id, call_id)
    if row is None:
        raise not_found("call")
    return row


async def detail(p: Principal, call_id: UUID) -> dict[str, Any]:
    row = await _call(p, call_id)
    turns = await repo.turns_for_call(call_id)
    t0 = (row.get("intervals") or {}).get("t0_ns") or 0
    rel = ("t_caller_first_voiced_ns", "t_caller_last_sample_ns", "t_agent_first_audio_ns", "t_agent_last_audio_ns")
    turns_out = []
    for t in turns:
        x = serialize.jsonable({k: v for k, v in t.items() if k not in ("id", "call_id")})
        for k in rel:
            x[k.replace("_ns", "_ms")] = round((t[k] - t0) / 1e6, 3) if t[k] is not None else None
            x.pop(k, None)
        turns_out.append(x)
    events = [{"t_ms": round((e["t_ns"] - t0) / 1e6, 3), "kind": e["kind"], "payload": e["payload"]}
              for e in await repo.events_for_call(call_id)]
    verdict = await repo.verdict_for_call(call_id)
    iv = row.get("intervals") or {}
    return {
        "call": serialize.call(row),
        "turns": turns_out,
        "events": events,
        "verdict": serialize.jsonable({k: v for k, v in verdict.items() if k != "id"}) if verdict else None,
        "intervals_ms": {k: [[round(a / 1e6, 3), round(b / 1e6, 3)] for a, b in iv.get(k, [])]
                         for k in ("caller", "agent", "windows")},
    }


async def audio(p: Principal, call_id: UUID) -> tuple[bytes | None, str | None]:
    row = await _call(p, call_id)
    if not row.get("audio_uri"):
        return None, None
    signed = ctx().storage.presign(row["audio_uri"])
    if signed:
        return None, signed
    return await ctx().storage.get(row["audio_uri"]), None


async def waveform(p: Principal, call_id: UUID) -> dict[str, Any]:
    row = await _call(p, call_id)
    if not row.get("waveform_uri"):
        return {"available": False, "reason": "audio unavailable — retention expired or upload failed"}
    data = await ctx().storage.get(row["waveform_uri"])
    return {"available": True, **json.loads(data)} if data else {"available": False, "reason": "artefact missing"}
