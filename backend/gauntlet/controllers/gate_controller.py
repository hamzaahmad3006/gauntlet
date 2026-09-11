"""Gate evaluation and history (SRS-FR-096, -097; API-052). A gate row is immutable once written."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from gauntlet.context import ctx
from gauntlet.controllers import serialize
from gauntlet.controllers.compare_controller import run_side
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.ids import new_id
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import ApiError, conflict
from gauntlet.scoring.compare import IncompatibleRuns
from gauntlet.scoring.gate import Ungatable, evaluate
from gauntlet.scoring.profile import ThresholdProfile


async def gate(p: Principal, run_id: UUID, baseline_run_id: UUID | None, tolerance: float | None) -> dict[str, Any]:
    run, cand = await run_side(p, run_id)
    target = await repo.one(T.targets, p.workspace_id, run["target_id"])
    base_id = baseline_run_id or (target or {}).get("baseline_run_id")
    if base_id is None:
        raise conflict("no_baseline", "no baseline is set for this target; promote a run first")
    _, base = await run_side(p, base_id)
    profile = ThresholdProfile.from_document(run["threshold_document"])
    report_url = f"{ctx().settings.app_base_url.rstrip('/')}/dashboard/runs/{run_id}"
    try:
        g = evaluate(cand, base, profile, tolerance, candidate_status=run["status"],
                     candidate_flags=run.get("flags") or [], report_url=report_url)
    except Ungatable as e:
        raise conflict("ungatable_run", str(e)) from None
    except IncompatibleRuns as e:
        raise ApiError(409, e.code, str(e), extra={"a": e.a, "b": e.b}) from None
    gid = new_id()
    async with repo.tx() as c:
        await c.execute(T.gates.insert().values(id=gid, workspace_id=p.workspace_id, run_id=run_id,
                                                baseline_run_id=base_id, verdict=g.verdict, breaches=g.breaches,
                                                markdown=g.markdown,
                                                tolerance=tolerance if tolerance is not None else profile.gate_tolerance_points))
        await repo.audit(c, p.workspace_id, p.actor, "gate.evaluated", f"run:{run_id}", {"verdict": g.verdict})
    return {"id": str(gid), "verdict": g.verdict, "breaches": g.breaches, "markdown": g.markdown,
            "score_delta": g.score_delta, "baseline_run_id": str(base_id), "run_id": str(run_id)}


async def history(p: Principal) -> list[dict[str, Any]]:
    return serialize.jsonable(await repo.gates(p.workspace_id))
