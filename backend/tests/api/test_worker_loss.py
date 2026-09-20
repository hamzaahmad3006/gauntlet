"""A call whose worker dies (SRS-FR-065, TC-065): it is retried once, then ends with `worker_lost`.

A worker that is killed mid-call stops renewing its concurrency lease. The sweeper reclaims expired leases:
the first time it re-queues the call, the second time it gives the call a terminal state and a reason,
because the rule is that every call leaves with exactly one terminal status and one reason. Nothing here
kills a real process — the lease is expired directly, which is the only thing the sweeper can observe.
"""

import uuid

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

DEV = {"Authorization": "Bearer dev"}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "development")
    from tests.conftest import database_url, reset_schema_if_postgres

    monkeypatch.setenv("DATABASE_URL", database_url(tmp_path, "worker.db"))
    monkeypatch.setenv("REDIS_URL", "")
    for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "SPEECHMATICS_API_KEY", "SUPABASE_URL"):
        monkeypatch.setenv(k, "")
    from gauntlet.common.settings import get_settings

    get_settings.cache_clear()
    from gauntlet.context import build_context, close_context

    await build_context(get_settings())
    await reset_schema_if_postgres()
    from gauntlet.server import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c
    await close_context()
    get_settings.cache_clear()


async def start_one_call(client) -> tuple[str, uuid.UUID]:
    """A run with a single call, taken to the state a worker holds it in: dialling, with a lease."""
    from gauntlet.context import ctx
    from gauntlet.db import repo
    from gauntlet.db import tables as T

    targets = (await client.get("/v1/targets", headers=DEV)).json()
    suites = (await client.get("/v1/suites", headers=DEV)).json()
    run = (await client.post("/v1/runs", headers=DEV, json={
        "target_id": targets[0]["id"], "suite_id": suites[0]["id"], "scenario_keys": ["book_table_basic"],
        "persona_keys": ["calm_standard"], "seed": 11})).json()["run"]
    async with repo.tx() as conn:
        call_id = (await conn.execute(sa.select(T.calls.c.id).where(T.calls.c.run_id == uuid.UUID(run["id"])))).scalar_one()
        await conn.execute(T.runs.update().where(T.runs.c.id == uuid.UUID(run["id"])).values(status="running"))
        await conn.execute(T.calls.update().where(T.calls.c.id == call_id)
                           .values(status="dialling", worker_id="worker-that-dies", started_at=repo.now()))
    assert await ctx().broker.acquire_slot(run["id"], str(call_id), limit=2, lease_s=300)
    return run["id"], call_id


async def kill_the_worker(run_id: str, call_id: uuid.UUID) -> None:
    """The only trace a killed worker leaves: a lease nobody renews. Expire it in the past."""
    import time

    from gauntlet.context import ctx

    b = ctx().broker
    await b.r.hset(f"run:{run_id}:slots", str(call_id), int((time.time() - 1) * 1000))
    assert str(call_id) in await b.expired_slots(run_id)


async def call_row(call_id: uuid.UUID) -> dict:
    from gauntlet.db import repo
    from gauntlet.db import tables as T

    async with repo.tx() as conn:
        return repo.d((await conn.execute(sa.select(T.calls).where(T.calls.c.id == call_id))).first())


async def test_tc065_a_lost_worker_retries_the_call_once_then_ends_it(client):
    from gauntlet.orchestrator.sweeper import sweep_once

    run_id, call_id = await start_one_call(client)

    # first loss: the call goes back into the queue for another worker, and counts an attempt
    await kill_the_worker(run_id, call_id)
    await sweep_once()
    row = await call_row(call_id)
    assert (row["status"], row["worker_id"]) == ("pending", None), row
    assert row["attempt"] == 2, row  # the retry is counted, and the schema allows only one

    # a second worker picks it up and dies too
    from gauntlet.context import ctx
    from gauntlet.db import repo
    from gauntlet.db import tables as T

    async with repo.tx() as conn:
        await conn.execute(T.calls.update().where(T.calls.c.id == call_id)
                           .values(status="in_call", worker_id="second-worker"))
    assert await ctx().broker.acquire_slot(run_id, str(call_id), limit=2, lease_s=300)
    await kill_the_worker(run_id, call_id)
    await sweep_once()

    row = await call_row(call_id)
    assert row["status"] == "errored"
    assert row["reason_code"] == "worker_lost"
    assert row["ended_at"] is not None  # one terminal status, one reason, one end (FR-065)

    # the run is finalised by the same sweep rather than left running for ever
    assert (await client.get(f"/v1/runs/{run_id}", headers=DEV)).json()["run"]["status"] in (
        "failed", "completed", "aborted")


async def test_a_renewed_lease_is_not_swept(client):
    """The sweeper must only reclaim calls nobody is working on: a live worker renews and keeps its call."""
    from gauntlet.context import ctx
    from gauntlet.orchestrator.sweeper import sweep_once

    run_id, call_id = await start_one_call(client)
    await kill_the_worker(run_id, call_id)
    await ctx().broker.renew_slot(run_id, str(call_id), lease_s=300)  # the worker is alive after all
    assert await ctx().broker.expired_slots(run_id) == []
    await sweep_once()

    row = await call_row(call_id)
    assert (row["status"], row["attempt"]) == ("dialling", 1), row  # untouched: still on its first attempt
