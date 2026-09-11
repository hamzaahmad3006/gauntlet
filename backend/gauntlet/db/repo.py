"""The single workspace-scoped data-access layer (SRS-FR-002, SRS 25.4).

Every function that reads or writes user data takes ``ws`` (the workspace id) first and applies the
predicate itself; no route composes SQL. A row belonging to another workspace simply does not exist
from the caller's point of view, which the API turns into 404 — never 403 — so identifiers are not
confirmed to exist. All queries are parameterised SQLAlchemy Core (SRS-SEC-005).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from gauntlet.context import ctx
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id


def now() -> datetime:
    return datetime.now(UTC)


def d(row: Any) -> dict[str, Any] | None:
    return dict(row._mapping) if row is not None else None


def ds(rows: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in rows]


@asynccontextmanager
async def tx() -> AsyncIterator[AsyncConnection]:
    async with ctx().engine.begin() as conn:
        yield conn


# -- identity ---------------------------------------------------------------------------------------
async def ensure_user(subject: str, login: str | None, email: str | None) -> dict[str, Any]:
    async with tx() as c:
        row = d((await c.execute(sa.select(T.users).where(T.users.c.auth_subject == subject))).first())
        if row:
            return row
    from gauntlet.db.seed import seed_workspace

    async with tx() as c:  # one transaction: no half-provisioned workspace can exist (SRS 7 A)
        row = d((await c.execute(sa.select(T.users).where(T.users.c.auth_subject == subject))).first())
        if row:
            return row
        ws_id, user_id = new_id(), new_id()
        await c.execute(T.workspaces.insert().values(id=ws_id, name=(login or "workspace")[:80]))
        await c.execute(T.users.insert().values(id=user_id, workspace_id=ws_id, auth_subject=subject,
                                                github_login=login, email=email))
        await seed_workspace(c, ws_id)
        await audit(c, ws_id, f"user:{user_id}", "workspace.created", f"workspace:{ws_id}", {})
        return {"id": user_id, "workspace_id": ws_id, "auth_subject": subject, "github_login": login, "email": email}


async def workspace(ws: UUID) -> dict[str, Any] | None:
    async with tx() as c:
        return d((await c.execute(sa.select(T.workspaces).where(T.workspaces.c.id == ws))).first())


async def audit(c: AsyncConnection, ws: UUID, actor: str, action: str, resource: str, payload: dict[str, Any]) -> None:
    await c.execute(T.audit_events.insert().values(workspace_id=ws, actor=actor, action=action, resource=resource,
                                                   payload=payload))


async def api_key_by_prefix(prefix: str) -> dict[str, Any] | None:
    async with tx() as c:
        return d((await c.execute(sa.select(T.api_keys).where(T.api_keys.c.prefix == prefix))).first())


async def touch_api_key(key_id: UUID) -> None:
    async with tx() as c:
        await c.execute(T.api_keys.update().where(T.api_keys.c.id == key_id).values(last_used_at=now()))


# -- generic scoped reads -----------------------------------------------------------------------------
async def one(table: sa.Table, ws: UUID, id_: UUID) -> dict[str, Any] | None:
    async with tx() as c:
        return d((await c.execute(sa.select(table).where(table.c.id == id_, table.c.workspace_id == ws))).first())


async def run_row(ws: UUID, run_id: UUID) -> dict[str, Any] | None:
    return await one(T.runs, ws, run_id)


async def call_row(ws: UUID, call_id: UUID) -> dict[str, Any] | None:
    async with tx() as c:
        q = (sa.select(T.calls).join(T.runs, T.runs.c.id == T.calls.c.run_id)
             .where(T.calls.c.id == call_id, T.runs.c.workspace_id == ws))
        return d((await c.execute(q)).first())


async def targets(ws: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.targets).where(T.targets.c.workspace_id == ws).order_by(T.targets.c.created_at)
        return ds((await c.execute(q)).all())


async def suites(ws: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.suites).where(T.suites.c.workspace_id == ws).order_by(T.suites.c.created_at.desc())
        return ds((await c.execute(q)).all())


async def suite_children(suite_id: UUID) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with tx() as c:
        sc = ds((await c.execute(sa.select(T.scenarios).where(T.scenarios.c.suite_id == suite_id))).all())
        pe = ds((await c.execute(sa.select(T.personas).where(T.personas.c.suite_id == suite_id))).all())
        return sc, pe


async def condition_profiles(ws: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.condition_profiles).where(T.condition_profiles.c.workspace_id == ws)
        return ds((await c.execute(q)).all())


async def condition_profile(ws: UUID, key: str) -> dict[str, Any] | None:
    async with tx() as c:
        q = sa.select(T.condition_profiles).where(T.condition_profiles.c.workspace_id == ws,
                                                  T.condition_profiles.c.key == key)
        return d((await c.execute(q)).first())


async def threshold_profile(ws: UUID, key: str) -> dict[str, Any] | None:
    async with tx() as c:
        q = (sa.select(T.threshold_profiles)
             .where(T.threshold_profiles.c.workspace_id == ws, T.threshold_profiles.c.key == key)
             .order_by(T.threshold_profiles.c.created_at.desc()))
        return d((await c.execute(q)).first())


async def threshold_profiles(ws: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.threshold_profiles).where(T.threshold_profiles.c.workspace_id == ws)
        return ds((await c.execute(q)).all())


async def runs(ws: UUID, target_id: UUID | None, status: str | None, limit: int,
               cursor: datetime | None) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.runs).where(T.runs.c.workspace_id == ws)
        if target_id:
            q = q.where(T.runs.c.target_id == target_id)
        if status:
            q = q.where(T.runs.c.status == status)
        if cursor:
            q = q.where(T.runs.c.created_at < cursor)
        q = q.order_by(T.runs.c.created_at.desc()).limit(limit)
        return ds((await c.execute(q)).all())


async def calls_for_run(ws: UUID, run_id: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = (sa.select(T.calls).join(T.runs, T.runs.c.id == T.calls.c.run_id)
             .where(T.calls.c.run_id == run_id, T.runs.c.workspace_id == ws)
             .order_by(T.calls.c.scenario_key, T.calls.c.persona_key, T.calls.c.repeat_index))
        return ds((await c.execute(q)).all())


async def turns_for_call(call_id: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.turns).where(T.turns.c.call_id == call_id).order_by(T.turns.c.idx)
        return ds((await c.execute(q)).all())


async def turns_for_run(run_id: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = (sa.select(T.turns, T.calls.c.status.label("call_status"))
             .join(T.calls, T.calls.c.id == T.turns.c.call_id).where(T.calls.c.run_id == run_id))
        return ds((await c.execute(q)).all())


async def events_for_call(call_id: UUID, limit: int = 2000) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.call_events).where(T.call_events.c.call_id == call_id).order_by(T.call_events.c.t_ns).limit(limit)
        return ds((await c.execute(q)).all())


async def verdict_for_call(call_id: UUID) -> dict[str, Any] | None:
    async with tx() as c:
        return d((await c.execute(sa.select(T.verdicts).where(T.verdicts.c.call_id == call_id))).first())


async def verdicts_for_run(run_id: UUID) -> dict[UUID, dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.verdicts).join(T.calls, T.calls.c.id == T.verdicts.c.call_id).where(T.calls.c.run_id == run_id)
        return {r["call_id"]: r for r in ds((await c.execute(q)).all())}


async def run_metrics(run_id: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.run_metrics).where(T.run_metrics.c.run_id == run_id).order_by(T.run_metrics.c.name)
        return ds((await c.execute(q)).all())


async def gates(ws: UUID, limit: int = 50) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.gates).where(T.gates.c.workspace_id == ws).order_by(T.gates.c.created_at.desc()).limit(limit)
        return ds((await c.execute(q)).all())


async def share_links(ws: UUID, run_id: UUID) -> list[dict[str, Any]]:
    async with tx() as c:
        q = sa.select(T.share_links).where(T.share_links.c.workspace_id == ws, T.share_links.c.run_id == run_id)
        return ds((await c.execute(q)).all())


async def share_by_token(token: str) -> dict[str, Any] | None:
    async with tx() as c:
        q = sa.select(T.share_links).where(T.share_links.c.token == token, T.share_links.c.revoked_at.is_(None),
                                           T.share_links.c.expires_at > now())
        return d((await c.execute(q)).first())


async def latest_clean_run(ws: UUID, target_id: UUID, suite_hash: str, definitions: str,
                           exclude: UUID) -> dict[str, Any] | None:
    """The clean reference for the degradation ratio (MET-15)."""
    async with tx() as c:
        q = (sa.select(T.runs).where(T.runs.c.workspace_id == ws, T.runs.c.target_id == target_id,
                                     T.runs.c.suite_version_hash == suite_hash, T.runs.c.definitions_version == definitions,
                                     T.runs.c.condition_profile_key == "clean", T.runs.c.status == "completed",
                                     T.runs.c.id != exclude)
             .order_by(T.runs.c.created_at.desc()).limit(1))
        return d((await c.execute(q)).first())


async def running_runs() -> list[dict[str, Any]]:
    async with tx() as c:
        return ds((await c.execute(sa.select(T.runs).where(T.runs.c.status.in_(("queued", "running"))))).all())


async def trailing_spend(ws: UUID, hours: int = 24) -> float:
    async with tx() as c:
        q = sa.select(sa.func.coalesce(sa.func.sum(T.runs.c.rig_cost_usd), 0.0)).where(
            T.runs.c.workspace_id == ws, T.runs.c.created_at > now() - timedelta(hours=hours))
        return float((await c.execute(q)).scalar() or 0.0)


async def active_run_count(ws: UUID) -> int:
    async with tx() as c:
        q = sa.select(sa.func.count()).select_from(T.runs).where(T.runs.c.workspace_id == ws,
                                                                   T.runs.c.status.in_(("queued", "running")))
        return int((await c.execute(q)).scalar() or 0)
