"""Health, readiness, principal and system status (API-001, API-070, API-071)."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from gauntlet.context import ctx
from gauntlet.controllers.serialize import jsonable
from gauntlet.db import repo
from gauntlet.metrics import disclosures
from gauntlet.metrics.definitions import DEFINITIONS_VERSION, METRICS
from gauntlet.middleware.auth import Principal


def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def readyz() -> tuple[dict[str, Any], bool]:
    c = ctx()
    db_ok = True
    try:
        async with c.engine.connect() as conn:
            await conn.execute(sa.text("select 1"))
    except Exception:
        db_ok = False
    redis_ok = await c.broker.ping()
    body = {"database": "ok" if db_ok else "down", "redis": "ok" if redis_ok else "down",
            "redis_mode": "in_process" if c.broker.in_process else "external", "storage": c.storage.kind}
    return body, db_ok and redis_ok


async def me(p: Principal) -> dict[str, Any]:
    ws = await repo.workspace(p.workspace_id)
    return {"principal": {"kind": p.kind, "login": p.login, "key_prefix": p.key_prefix},
            "workspace": jsonable({k: ws[k] for k in ("id", "name", "audio_retention_days", "daily_spend_cap_usd",
                                                       "max_concurrent_runs")}) if ws else None,
            "scopes": sorted(p.scopes)}


def system() -> dict[str, Any]:
    s = ctx().settings
    return {
        "environment": s.environment,
        "providers": s.providers,
        "auth": {"supabase_url": s.supabase_url, "supabase_anon_key": s.supabase_anon_key,
                 "dev_login": s.is_dev or s.allow_guest, "guest": s.allow_guest and not s.is_dev},
        "definitions_version": DEFINITIONS_VERSION,
        "metrics": {k: {"met_id": m.met_id, "label": m.label, "unit": m.unit, "direction": m.direction,
                        "definition": m.definition} for k, m in METRICS.items()},
        "disclosures": disclosures.ALL,
        "limits": {"max_concurrent_calls": s.max_concurrent_calls, "max_calls_per_run": s.max_calls_per_run,
                   "default_spend_cap_usd": s.default_run_spend_cap_usd},
        "calibration": ctx().calibration,
        "rig_benchmark": ctx().rig_benchmark,
    }


def calibration() -> dict[str, Any]:
    cal = ctx().calibration
    if not cal:
        return {"bound_ms": None, "method": None, "note": "no committed calibration artefact"}
    return {**cal, "scope_statement": disclosures.CALIBRATION_SCOPE,
            "evidence": "MEASURED — raw rows committed in calibration/results.csv"}
