"""API tests against a real app with SQLite and in-process Redis (TC-001..003, TC-010, TC-013, TC-020,
TC-023, TC-111, TC-120). No external provider is touched."""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "")
    for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "SPEECHMATICS_API_KEY", "SUPABASE_URL"):
        monkeypatch.setenv(k, "")
    from gauntlet.common.settings import get_settings

    get_settings.cache_clear()
    from gauntlet.context import build_context, close_context

    await build_context(get_settings())
    from gauntlet.server import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_context()
    get_settings.cache_clear()


DEV = {"Authorization": "Bearer dev"}


async def test_tc001_first_sign_in_seeds_workspace(client):
    r = await client.get("/v1/me", headers=DEV)
    assert r.status_code == 200
    targets = (await client.get("/v1/targets", headers=DEV)).json()
    assert len(targets) == 2 and all(t["verified_at"] for t in targets)
    suites = (await client.get("/v1/suites", headers=DEV)).json()
    assert suites[0]["key"] == "booking-core" and len(suites[0]["scenarios"]) == 6
    conds = [c["key"] for c in (await client.get("/v1/condition-profiles", headers=DEV)).json()]
    assert conds == ["clean", "mobile", "hostile", "turn_taking"]


async def test_unauthenticated_is_401_with_envelope(client):
    r = await client.get("/v1/targets")
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "unauthenticated" and body["correlation_id"]


async def test_tc003_key_scopes_and_one_time_plaintext(client):
    r = await client.post("/v1/api-keys", headers=DEV, json={"name": "ci", "scopes": ["run:read"]})
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("gnt_")
    listed = (await client.get("/v1/api-keys", headers=DEV)).json()
    assert "key" not in listed[0] and "hash" not in listed[0]
    kh = {"Authorization": f"Bearer {key}"}
    assert (await client.get("/v1/runs", headers=kh)).status_code == 200
    targets = (await client.get("/v1/targets", headers=kh)).json()
    suites = (await client.get("/v1/suites", headers=kh)).json()
    r = await client.post("/v1/runs", headers=kh, json={"target_id": targets[0]["id"], "suite_id": suites[0]["id"]})
    assert r.status_code == 403 and r.json()["error"]["missing_scope"] == "run:create"
    # keys can never mint keys or create targets (SRS 25.3)
    assert (await client.post("/v1/api-keys", headers=kh, json={"name": "x", "scopes": ["run:read"]})).status_code == 403
    kid = listed[0]["id"]
    assert (await client.delete(f"/v1/api-keys/{kid}", headers=DEV)).status_code == 204
    assert (await client.get("/v1/runs", headers=kh)).status_code == 401  # revocation on the next request


async def test_tc002_cross_workspace_reads_are_404(client, monkeypatch):
    targets = (await client.get("/v1/targets", headers=DEV)).json()
    # a second workspace through the repository layer
    from gauntlet.db import repo

    other = await repo.ensure_user("test|other", "other", None)
    from gauntlet.middleware import auth

    real = auth.resolve

    async def fake(authorization):
        if authorization == "Bearer other":
            return auth.Principal("user", other["workspace_id"], user_id=other["id"])
        return await real(authorization)

    monkeypatch.setattr(auth, "resolve", fake)
    oh = {"Authorization": "Bearer other"}
    for path in (f"/v1/targets/{targets[0]['id']}", f"/v1/runs/{uuid.uuid4()}", f"/v1/calls/{uuid.uuid4()}"):
        assert (await client.get(path, headers=oh)).status_code == 404


async def test_tc120_ssrf_rejects_private_and_metadata(client):
    for url, cls in [("wss://127.0.0.1:9/x", None), ("wss://10.0.0.5/x", "private"),
                     ("wss://169.254.169.254/latest", "cloud_metadata"), ("ws://example.com/x", "scheme")]:
        r = await client.post("/v1/targets", headers=DEV, json={
            "name": f"t-{uuid.uuid4().hex[:6]}", "adapter": "websocket_pcm", "connection": {"url": url}})
        assert r.status_code == 422, (url, r.text)
        if cls:
            assert r.json()["error"].get("host_class") == cls or cls in r.text


async def test_tc010_tc013_adapter_immutable_and_unverified_blocks_runs(client):
    r = await client.post("/v1/targets", headers=DEV, json={
        "name": "local agent", "adapter": "websocket_pcm", "connection": {"url": "ws://127.0.0.1:9/agent"}})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["verified_at"] is None and "connection" not in t
    assert (await client.patch(f"/v1/targets/{t['id']}", headers=DEV, json={"adapter": "livekit"})).status_code == 409
    suites = (await client.get("/v1/suites", headers=DEV)).json()
    r = await client.post("/v1/runs", headers=DEV, json={"target_id": t["id"], "suite_id": suites[0]["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "target_not_verified"


async def test_tc020_suite_upload_reports_line(client):
    bad = "key: s\nscenarios:\n  - key: a\n    coverage_tag: nope\npersonas: []\n"
    r = await client.post("/v1/suites", headers=DEV, json={"yaml": bad})
    assert r.status_code == 422 and r.json()["error"]["line"] is not None


async def test_run_creation_is_idempotent_and_estimate_has_no_side_effects(client):
    targets = (await client.get("/v1/targets", headers=DEV)).json()
    suites = (await client.get("/v1/suites", headers=DEV)).json()
    body = {"target_id": targets[0]["id"], "suite_id": suites[0]["id"], "scenario_keys": ["book_table_basic"],
            "persona_keys": ["calm_standard"], "seed": 7}
    est = (await client.post("/v1/runs/estimate", headers=DEV, json=body)).json()
    assert est["calls"] == 1
    assert (await client.get("/v1/runs", headers=DEV)).json()["items"] == []
    h = {**DEV, "Idempotency-Key": "abc"}
    a = (await client.post("/v1/runs", headers=h, json=body)).json()["run"]
    b = (await client.post("/v1/runs", headers=h, json=body)).json()
    assert b["run"]["id"] == a["id"] and b["idempotent_replay"]
    assert a["seed"] == "7"
    await client.post(f"/v1/runs/{a['id']}/abort", headers=DEV)


async def test_public_calibration_and_system_need_no_auth(client):
    assert (await client.get("/v1/calibration")).status_code == 200
    s = (await client.get("/v1/system")).json()
    assert "impairment" in s["disclosures"] and s["metrics"]["barge_in_stop_p95"]["met_id"] == "MET-05"


def test_disclosure_is_referenced_by_every_render_path():
    """TC-056: the mandatory disclosure appears in the results payload, every report, and LIMITATIONS.md."""
    from gauntlet.metrics.disclosures import IMPAIRMENT_DISCLOSURE
    from gauntlet.reports import render

    assert IMPAIRMENT_DISCLOSURE in render.LIMITATIONS
    root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    doc = open(os.path.join(root, "docs", "LIMITATIONS.md"), encoding="utf-8").read().replace("\n> ", " ")
    assert "Adverse conditions are applied at the application layer" in doc
    src = open(os.path.join(root, "backend", "gauntlet", "controllers", "runs_controller.py"), encoding="utf-8").read()
    assert "IMPAIRMENT_DISCLOSURE" in src
