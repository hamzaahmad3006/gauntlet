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

from gauntlet.common.crypto import decrypt_json, encrypt_json
from gauntlet.context import ctx
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.suites.loader import Suite, bundled_conditions, bundled_suite, bundled_thresholds

BUNDLED_TARGETS = [
    {
        "name": "Bella Tavola — synthetic (tuned)",
        "description": "Reference booking agent fixture: Whisper STT → Qwen3.6 27B → TTS, 450 ms endpointing, yields "
                       "220 ms after barge-in. Without a Groq key it answers with scripted lines. A test fixture, "
                       "not a product.",
        "query": "mode=reference&model=qwen/qwen3.6-27b&endpoint_ms=450&delay_ms=250&yield_ms=220&greeting=1",
    },
    {
        "name": "Bella Tavola — synthetic (slow endpointing)",
        "description": "Same fixture, badly tuned: gpt-oss-120b, 900 ms endpointing, never yields to barge-in. Exists so "
                       "a real two-configuration comparison is available immediately.",
        "query": "mode=reference&model=openai/gpt-oss-120b&endpoint_ms=900&delay_ms=650&yield_ms=never&greeting=1",
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


async def refresh_bundled_targets() -> int:
    """Bring bundled targets in existing workspaces up to the current definitions. A workspace seeded by an
    older build keeps its old fixture query (for example scripted mode or a retired model) otherwise, and
    the bundled agent then never speaks real words. Only rows marked bundled are touched."""
    import sqlalchemy as sa

    from gauntlet.db.repo import now

    base = fixture_base_url()
    by_name = {t["name"]: t for t in BUNDLED_TARGETS}
    changed = 0
    async with ctx().engine.begin() as c:
        rows = (await c.execute(sa.select(T.targets.c.id, T.targets.c.name, T.targets.c.connection_encrypted,
                                          T.targets.c.connection_nonce).where(T.targets.c.bundled.is_(True)))).all()
        for row in rows:
            t = by_name.get(row.name)
            if t is None:
                continue
            url = f"{base}/fixtures/agent?{t['query']}"
            try:
                current = decrypt_json(ctx().key, row.connection_encrypted, row.connection_nonce).get("url")
            except Exception:
                current = None
            if current == url:
                continue
            blob, nonce = encrypt_json(ctx().key, {"url": url})
            await c.execute(T.targets.update().where(T.targets.c.id == row.id).values(
                connection_encrypted=blob, connection_nonce=nonce, connection_hint=f"{base}/fixtures/agent",
                description=t["description"], verified_at=now()))
            changed += 1
    return changed
