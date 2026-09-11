"""Workspace seed content (SRS 7 A, 45.2): the bundled suite, personas, four condition profiles, the
``default`` threshold profile, and two bundled synthetic targets. The dashboard is never empty.

The bundled targets are two *configurations* of the synthetic agent fixture served by this deployment at
``/fixtures/agent`` — one tuned well, one with slow endpointing and no barge-in yield — so a comparison
between two real configurations is possible from the first sign-in. They are labelled as fixtures.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import yaml
from sqlalchemy.ext.asyncio import AsyncConnection

from gauntlet.common.crypto import encrypt_json
from gauntlet.context import ctx
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.suites.loader import Suite, bundled_conditions, bundled_suite, bundled_thresholds

BUNDLED_TARGETS = [
    {
        "name": "Bella Tavola — synthetic (tuned)",
        "description": "Synthetic booking agent fixture: 450 ms endpointing, 250 ms processing, yields 220 ms after "
                       "barge-in. A test fixture, not a product.",
        "query": "mode=agent&endpoint_ms=450&delay_ms=250&yield_ms=220&greeting=1",
    },
    {
        "name": "Bella Tavola — synthetic (slow endpointing)",
        "description": "Same fixture, badly tuned: 900 ms endpointing, 650 ms processing, never yields to barge-in. "
                       "Exists so a real two-configuration comparison is available immediately.",
        "query": "mode=agent&endpoint_ms=900&delay_ms=650&yield_ms=never&greeting=1",
    },
]


def fixture_base_url() -> str:
    s = ctx().settings
    host = s.public_fixture_host or s.api_base_url
    host = host.rstrip("/")
    if host.startswith("https://"):
        return "wss://" + host[len("https://"):]
    if host.startswith("http://"):
        return "ws://" + host[len("http://"):]
    return host


async def insert_suite(c: AsyncConnection, ws: UUID, suite: Suite, yaml_source: str,
                       parent: UUID | None = None) -> UUID:
    suite_id = new_id()
    await c.execute(T.suites.insert().values(id=suite_id, workspace_id=ws, key=suite.key, name=suite.name,
                                             version_hash=suite.version_hash, parent_suite_id=parent,
                                             yaml_source=yaml_source, document=suite.document))
    for sc in suite.scenarios:
        timing = sc.get("timing") or {}
        await c.execute(T.scenarios.insert().values(
            id=new_id(), suite_id=suite_id, key=sc["key"], coverage_tag=sc["coverage_tag"], definition=sc,
            max_turns=int(timing.get("max_turns", 12)), max_duration_s=int(timing.get("max_duration_s", 120))))
    for p in suite.personas:
        await c.execute(T.personas.insert().values(
            id=new_id(), suite_id=suite_id, key=p["key"], voice_id=p["voice_id"], speech_rate=float(p["speech_rate"]),
            patience_s=int(p["patience_s"]), definition=p))
    return suite_id


async def seed_workspace(c: AsyncConnection, ws: UUID) -> dict[str, Any]:
    suite = bundled_suite()
    await insert_suite(c, ws, suite, yaml.safe_dump(suite.document, sort_keys=False, allow_unicode=True))
    for key, params in bundled_conditions().items():
        await c.execute(T.condition_profiles.insert().values(id=new_id(), workspace_id=ws, key=key, parameters=params))
    prof = bundled_thresholds()
    await c.execute(T.threshold_profiles.insert().values(id=new_id(), workspace_id=ws, key=prof.key,
                                                         version_hash=prof.version_hash, document=prof.source))
    base = fixture_base_url()
    from gauntlet.db.repo import now

    for t in BUNDLED_TARGETS:
        url = f"{base}/fixtures/agent?{t['query']}"
        blob, nonce = encrypt_json(ctx().key, {"url": url})
        await c.execute(T.targets.insert().values(
            id=new_id(), workspace_id=ws, name=t["name"], adapter="websocket_pcm", description=t["description"],
            bundled=True, connection_encrypted=blob, connection_nonce=nonce, connection_hint=f"{base}/fixtures/agent",
            verified_at=now()))
    return {"suite": suite.key}
