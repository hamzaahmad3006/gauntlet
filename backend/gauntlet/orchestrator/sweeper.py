"""Orphan sweeper (SRS 29): every 30 s reclaim expired concurrency leases, mark their calls errored with
``worker_lost`` (re-queueing once while attempt < 2), reconcile runs whose calls are all terminal, and
abort runs exceeding MAX_RUN_DURATION_S. Also deletes expired audio (retention, SRS-NFR-032)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa

from gauntlet.context import ctx
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.orchestrator.lifecycle import finalize_run

log = logging.getLogger("gauntlet.sweeper")


async def sweep_once() -> None:
    c = ctx()
    b = c.broker
    for run in await repo.running_runs():
        rid = str(run["id"])
        for slot in await b.expired_slots(rid):
            await b.release_slot(rid, slot)
            call_id = UUID(slot)  # leases are keyed by string; the database wants the identifier itself
            async with repo.tx() as conn:
                row = repo.d((await conn.execute(sa.select(T.calls).where(T.calls.c.id == call_id))).first())
                if row and row["status"] in ("dialling", "in_call"):
                    if row["attempt"] < 2:
                        await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(
                            status="pending", attempt=row["attempt"] + 1, worker_id=None))
                        await b.enqueue(rid, slot)
                    else:
                        await conn.execute(T.calls.update().where(T.calls.c.id == call_id).values(
                            status="errored", reason_code="worker_lost", ended_at=repo.now()))
        started = run.get("started_at") or run.get("created_at")
        if started and repo.now() - started.replace(tzinfo=started.tzinfo or repo.now().tzinfo) > timedelta(
                seconds=c.settings.max_run_duration_s):
            await b.set_abort(rid)
            async with repo.tx() as conn:
                await conn.execute(T.calls.update().where(T.calls.c.run_id == run["id"],
                                                          T.calls.c.status == "pending")
                                   .values(status="errored", reason_code="run_aborted", ended_at=repo.now()))
        await finalize_run(run["id"])
    # retention: delete expired audio, keep the call row and its metrics
    async with repo.tx() as conn:
        rows = repo.ds((await conn.execute(sa.select(T.calls.c.id, T.calls.c.audio_uri, T.calls.c.waveform_uri)
                                           .where(T.calls.c.expires_at < repo.now(), T.calls.c.audio_uri.is_not(None))
                                           .limit(200))).all())
    for r in rows:
        for uri in (r["audio_uri"], r["waveform_uri"]):
            if uri:
                await c.storage.delete(uri)
        async with repo.tx() as conn:
            await conn.execute(T.calls.update().where(T.calls.c.id == r["id"]).values(audio_uri=None, waveform_uri=None))
            await conn.execute(T.turns.update().where(T.turns.c.call_id == r["id"]).values(agent_text=None))


async def sweep_forever(stop: asyncio.Event, interval_s: float = 30.0) -> None:
    while not stop.is_set():
        with contextlib.suppress(Exception):
            await sweep_once()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_s)
