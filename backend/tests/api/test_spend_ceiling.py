"""The spend ceiling (SRS-FR-035): a run stops when its rig cost reaches the cap, and says why.

No provider is billed here. The worker charges what a call has cost so far through the broker and aborts the
run with the reason ``budget`` (``worker/executor.py``); these tests drive that same accounting and then let
the run finalise, which is where the reason becomes the run's terminal status.
"""

import pytest
from httpx import ASGITransport, AsyncClient

DEV = {"Authorization": "Bearer dev"}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "development")
    from tests.conftest import database_url, reset_schema_if_postgres

    monkeypatch.setenv("DATABASE_URL", database_url(tmp_path, "spend.db"))
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


async def make_run(client, spend_cap: float) -> str:
    targets = (await client.get("/v1/targets", headers=DEV)).json()
    suites = (await client.get("/v1/suites", headers=DEV)).json()
    body = {"target_id": targets[0]["id"], "suite_id": suites[0]["id"], "scenario_keys": ["book_table_basic"],
            "persona_keys": ["calm_standard"], "spend_cap_usd": spend_cap, "seed": 5}
    r = await client.post("/v1/runs", headers=DEV, json=body)
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert float(run["spend_cap_usd"]) == spend_cap
    return run["id"]


async def stop_calls(run_id: str, reason: str) -> None:
    """What the worker does once the run is aborted: every call it holds gets a terminal state and reason."""
    from uuid import UUID

    from gauntlet.db import repo
    from gauntlet.worker.executor import _terminate

    run = UUID(run_id)
    async with repo.tx() as conn:
        import sqlalchemy as sa

        from gauntlet.db import tables as T

        rows = (await conn.execute(sa.select(T.calls.c.id).where(T.calls.c.run_id == run))).all()
    for (call_id,) in rows:
        await _terminate(call_id, run, reason)


async def spend_up_to_cap(run_id: str, cap: float) -> bool:
    """What the worker does at a turn boundary: charge the delta, then stop the run if the cap is reached."""
    from gauntlet.context import ctx

    b = ctx().broker
    spent = await b.add_spend(run_id, cap / 2)
    assert spent < cap, "half the cap is not the cap"
    spent = await b.add_spend(run_id, cap / 2)
    if spent >= cap:
        await b.r.set(f"run:{run_id}:abort_reason", "budget", ex=86_400)
        await b.set_abort(run_id)
        return False
    return True


async def test_tc035_a_run_stops_at_its_spend_cap_and_says_why(client):
    from gauntlet.orchestrator.lifecycle import finalize_run
    from uuid import UUID

    run_id = await make_run(client, 0.25)
    assert await spend_up_to_cap(run_id, 0.25) is False  # the second charge reaches the cap
    await stop_calls(run_id, "run_aborted")
    await finalize_run(UUID(run_id))

    s = (await client.get(f"/v1/runs/{run_id}", headers=DEV)).json()
    assert s["run"]["status"] == "aborted_budget", s["run"]["status"]

    # a budget stop is not a result: the gate refuses to judge it rather than calling it a regression
    from gauntlet.scoring.gate import UNGATABLE_STATUSES

    assert "aborted_budget" in UNGATABLE_STATUSES


async def test_a_run_aborted_by_hand_is_not_reported_as_a_budget_stop(client):
    """The status must carry the reason: the same abort without the budget marker reads as `aborted`."""
    from uuid import UUID

    from gauntlet.context import ctx
    from gauntlet.orchestrator.lifecycle import finalize_run

    run_id = await make_run(client, 2.0)
    await ctx().broker.set_abort(run_id)
    await stop_calls(run_id, "run_aborted")
    await finalize_run(UUID(run_id))
    assert (await client.get(f"/v1/runs/{run_id}", headers=DEV)).json()["run"]["status"] == "aborted"


async def test_spending_below_the_cap_leaves_the_run_running(client):
    from gauntlet.context import ctx

    run_id = await make_run(client, 1.0)
    b = ctx().broker
    await b.add_spend(run_id, 0.1)
    await b.add_spend(run_id, 0.2)
    assert await b.spend(run_id) == pytest.approx(0.3)
    assert await b.aborted(run_id) is False
    assert (await client.get(f"/v1/runs/{run_id}", headers=DEV)).json()["run"]["status"] in ("queued", "running")


def test_the_charge_is_arithmetic_over_the_counters():
    """SRS 20.2: what the worker charges is a deterministic function of the call's counters and the price
    list, so a cap is reached at a predictable point rather than at a provider's discretion."""
    from gauntlet.cost.calculator import PriceEntry, Pricing, RigCounters, rig_cost

    pricing = Pricing({
        "caller_llm": {"prompt_tokens": PriceEntry(price=1.0, unit="per_1k_tokens"),
                       "completion_tokens": PriceEntry(price=2.0, unit="per_1k_tokens")},
        "caller_tts": {"characters": PriceEntry(price=4.0, unit="per_1k_characters")},
    }, unknown_unit_cost_usd=0.0)
    counters = RigCounters(llm_prompt_tokens=1000, llm_completion_tokens=500, tts_characters=250)
    first = rig_cost(counters, pricing)["total_usd"]
    assert first == pytest.approx(1.0 + 1.0 + 1.0)  # 1k prompt + 0.5k completion + 0.25k characters
    assert rig_cost(counters, pricing)["total_usd"] == first  # same counters, same charge
