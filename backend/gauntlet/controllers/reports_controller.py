"""Reports, Markdown export, share links, public report (SRS-FR-110..112; API-041..044)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from gauntlet.common.crypto import new_token
from gauntlet.context import ctx
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import not_found
from gauntlet.reports import render


async def _data(ws: UUID, run_id: UUID, public: bool) -> dict[str, Any]:
    run = await repo.run_row(ws, run_id)
    if run is None:
        raise not_found("run")
    target = await repo.one(T.targets, ws, run["target_id"])
    suite = await repo.one(T.suites, ws, run["suite_id"])
    calls = await repo.calls_for_run(ws, run_id)
    return render.build(run, await repo.run_metrics(run_id), target["name"] if target else "target",
                        suite["name"] if suite else "suite", ctx().calibration, public=public, calls=calls,
                        declaration=None if public else (target or {}).get("pipeline_declaration"))


async def report(p: Principal, run_id: UUID, fmt: str) -> Any:
    data = await _data(p.workspace_id, run_id, public=False)
    if fmt == "md":
        return render.to_markdown(data)
    if fmt == "html":
        return render.to_html(data)
    return data


async def share(p: Principal, run_id: UUID, days: int) -> dict[str, Any]:
    if await repo.run_row(p.workspace_id, run_id) is None:
        raise not_found("run")
    token = new_token(32)
    async with repo.tx() as c:
        await c.execute(T.share_links.insert().values(id=new_id(), run_id=run_id, workspace_id=p.workspace_id,
                                                      token=token, expires_at=repo.now() + timedelta(days=days)))
        await c.execute(T.runs.update().where(T.runs.c.id == run_id).values(pinned=True))
        await repo.audit(c, p.workspace_id, p.actor, "share.created", f"run:{run_id}", {})
    s = ctx().settings
    return {"token": token, "url": f"{s.app_base_url.rstrip('/')}/r/{token}",
            "html_url": f"{s.api_base_url.rstrip('/')}/public/reports/{token}"}


async def revoke_share(p: Principal, run_id: UUID) -> dict[str, Any]:
    async with repo.tx() as c:
        res = await c.execute(T.share_links.update().where(T.share_links.c.run_id == run_id,
                                                           T.share_links.c.workspace_id == p.workspace_id,
                                                           T.share_links.c.revoked_at.is_(None))
                              .values(revoked_at=repo.now()))
        await repo.audit(c, p.workspace_id, p.actor, "share.revoked", f"run:{run_id}", {})
    return {"revoked": res.rowcount}


async def public_report(token: str, fmt: str) -> Any:
    link = await repo.share_by_token(token)
    if link is None:
        raise not_found("report")  # revoked or expired: 404, never 410 (SRS-FR-111)
    data = await _data(link["workspace_id"], link["run_id"], public=True)
    return render.to_html(data) if fmt == "html" else data
