"""Run lifecycle through the API with a real in-process worker and a real fixture WebSocket server
(TC-012, TC-013, TC-014, TC-030, TC-036, TC-037, TC-038, TC-039, TC-095, TC-110, TC-111, TC-112)."""

import asyncio
import json
import socket

import pytest
from httpx import ASGITransport, AsyncClient

from fixtures.calibration_target.server import serve

pytestmark = pytest.mark.realtime
DEV = {"Authorization": "Bearer dev"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GAUNTLET_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'lc.db').as_posix()}")
    for k in ("REDIS_URL", "GROQ_API_KEY", "ELEVENLABS_API_KEY", "SPEECHMATICS_API_KEY", "SUPABASE_URL"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("MAX_CALLS_PER_WORKER", "6")
    monkeypatch.setenv("GREETING_WAIT_MS", "1000")
    from gauntlet.common.settings import get_settings

    get_settings.cache_clear()
    from gauntlet.context import build_context, close_context
    from gauntlet.server import create_app
    from gauntlet.worker.main import worker_loop

    await build_context(get_settings())
    port = free_port()
    server = await serve("127.0.0.1", port)
    stop = asyncio.Event()
    worker = asyncio.create_task(worker_loop(stop, "test-worker"))
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test", timeout=90) as c:
        yield c, port
    stop.set()
    worker.cancel()
    server.close()
    await close_context()
    get_settings.cache_clear()


async def make_target(c, port, name, query):
    r = await c.post("/v1/targets", headers=DEV, json={"name": name, "adapter": "websocket_pcm",
                                                      "connection": {"url": f"ws://127.0.0.1:{port}/?{query}"}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def wait_terminal(c, run_id, timeout=180):
    for _ in range(timeout):
        s = (await c.get(f"/v1/runs/{run_id}", headers=DEV)).json()
        if s["run"]["status"] in ("completed", "aborted", "aborted_budget", "failed"):
            return s
        await asyncio.sleep(1)
    raise AssertionError("run did not finish")


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    out = []
    for chunk in raw.split("\n\n"):
        if "data: " not in chunk:
            continue
        eid = chunk.split("id: ")[1].split("\n")[0] if "id: " in chunk else ""
        out.append((eid, json.loads(chunk.split("data: ", 1)[1])))
    return out


async def test_tc012_tc013_tc014_verify_and_diagnose(env):
    c, port = env
    tid = await make_target(c, port, "scripted agent", "mode=agent&endpoint_ms=400&delay_ms=100&greeting=1")
    suite = (await c.get("/v1/suites", headers=DEV)).json()[0]["id"]
    blocked = await c.post("/v1/runs", headers=DEV, json={"target_id": tid, "suite_id": suite})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "target_not_verified"
    v = (await c.post(f"/v1/targets/{tid}/verify", headers=DEV)).json()
    assert v["verified_at"], v  # the fixture echoes the nonce in its hello
    d = (await c.post(f"/v1/targets/{tid}/diagnose", headers=DEV)).json()
    assert d["connection"]["status"] == "ok" and d["audio_out"]["status"] == "ok", d
    assert d["audio_in"]["status"] == "ok", d
    assert d["transcript"]["status"] == "not_configured"
    sid = await make_target(c, port, "silent agent", "mode=silent")
    await c.post(f"/v1/targets/{sid}/verify", headers=DEV)
    ds = (await c.post(f"/v1/targets/{sid}/diagnose", headers=DEV)).json()
    assert ds["connection"]["status"] == "ok" and ds["audio_in"]["status"] == "failed", ds
    assert "never spoke" in ds["audio_in"]["hint"]
    # editing the connection revokes verification (SRS-FR-013)
    await c.patch(f"/v1/targets/{tid}", headers=DEV, json={"connection": {"url": f"ws://127.0.0.1:{port}/?mode=echo"}})
    assert (await c.get(f"/v1/targets/{tid}", headers=DEV)).json()["verified_at"] is None


async def test_run_events_injection_reports_share_and_abort(env):
    c, port = env
    tid = await make_target(c, port, "tuned agent", "mode=agent&endpoint_ms=400&delay_ms=150&yield_ms=200")
    await c.post(f"/v1/targets/{tid}/verify", headers=DEV)
    suite = (await c.get("/v1/suites", headers=DEV)).json()[0]["id"]
    body = {"target_id": tid, "suite_id": suite, "condition_profile_key": "turn_taking", "concurrency": 2,
            "scenario_keys": ["book_table_basic"], "persona_keys": ["calm_standard", "fast_mobile"], "seed": 99}
    run = (await c.post("/v1/runs", headers=DEV, json=body)).json()["run"]
    assert run["seed"] == "99" and run["total_calls"] == 2  # TC-030

    await asyncio.sleep(6)
    inj = await c.post(f"/v1/runs/{run['id']}/conditions", headers=DEV, json={"profile_key": "mobile"})
    assert inj.status_code == 200 and inj.json()["epoch"] == 1  # TC-038
    s = await wait_terminal(c, run["id"])
    assert s["run"]["status"] == "completed", s["run"]
    assert [e["epoch"] for e in s["run"]["epochs"]] == [0, 1]
    assert any(m["name"] == "response_latency_p95" and m["value"] for m in s["metrics"])

    # TC-037: the event stream replays from Last-Event-ID with contiguous sequence numbers
    events = parse_sse((await c.get(f"/v1/runs/{run['id']}/events", headers=DEV)).text)
    kinds = [e["kind"] for _, e in events]
    assert kinds[0] == "run.started" and "run.completed" in kinds and "chaos.changed" in kinds
    seqs = [e["seq"] for _, e in events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    cut_id, cut = events[4]
    replay = parse_sse((await c.get(f"/v1/runs/{run['id']}/events", headers={**DEV, "Last-Event-ID": cut_id})).text)
    assert [e["seq"] for _, e in replay] == list(range(cut["seq"] + 1, seqs[-1] + 1))

    # TC-110 / TC-112 reports
    rep = (await c.get(f"/v1/runs/{run['id']}/report.json", headers=DEV)).json()
    assert rep["metrics"] and all(m["evidence"] in ("MEASURED", "ESTIMATED") for m in rep["metrics"])
    assert rep["limitations"] and rep["independence"]["referee_engines"] == []
    md = (await c.get(f"/v1/runs/{run['id']}/report.md", headers=DEV)).text
    assert "| Metric | Value | Threshold |" in md and "## Limitations" in md

    # TC-111 share link: public, no workspace identifier, revocable to 404
    share = (await c.post(f"/v1/runs/{run['id']}/share", headers=DEV, json={})).json()
    pub = await c.get(f"/public/reports/{share['token']}.json")
    me = (await c.get("/v1/me", headers=DEV)).json()
    assert pub.status_code == 200 and me["workspace"]["id"] not in pub.text
    await c.delete(f"/v1/runs/{run['id']}/share", headers=DEV)
    assert (await c.get(f"/public/reports/{share['token']}.json")).status_code == 404

    # TC-095: an ungraded run (2 calls, fewer than 20) can never become a baseline
    bad = await c.post(f"/v1/targets/{tid}/baseline", headers=DEV, json={"run_id": run["id"]})
    assert bad.status_code == 409

    # TC-039 filters
    listed = (await c.get(f"/v1/runs?target_id={tid}&status=completed", headers=DEV)).json()["items"]
    assert [r["id"] for r in listed] == [run["id"]]

    # TC-036 abort: workers stop and partial results persist
    run2 = (await c.post("/v1/runs", headers=DEV, json={**body, "scenario_keys": None, "persona_keys": None,
                                                           "concurrency": 2})).json()["run"]
    await asyncio.sleep(4)
    assert (await c.post(f"/v1/runs/{run2['id']}/abort", headers=DEV)).status_code == 200
    s2 = await wait_terminal(c, run2["id"], timeout=60)
    assert s2["run"]["status"] == "aborted"
    assert any(cl["reason_code"] == "run_aborted" for cl in s2["calls"])

    metrics = (await c.get("/metrics")).text
    assert "gauntlet_api_requests_total" in metrics and "gauntlet_calls_total" in metrics
