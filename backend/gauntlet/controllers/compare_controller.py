"""Run comparison and recommendation (SRS-FR-093, -094; API-050)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from gauntlet.db import repo
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import ApiError, not_found
from gauntlet.scoring.compare import IncompatibleRuns, RunSide, compare
from gauntlet.scoring.profile import ThresholdProfile


async def run_side(p: Principal, run_id: UUID) -> tuple[dict[str, Any], RunSide]:
    run = await repo.run_row(p.workspace_id, run_id)
    if run is None:
        raise not_found("run")
    mets = {m["name"]: m["value"] for m in await repo.run_metrics(run_id) if m["epoch"] is None}
    score = run.get("score") or {}
    subs = {s["id"]: s["score"] for s in score.get("subscores", [])}
    return run, RunSide(str(run_id), run["suite_version_hash"], run["threshold_version_hash"], run["definitions_version"],
                        mets, run.get("overall"), run.get("grade"), "hard_breach" in (run.get("flags") or []), subs,
                        mets.get("est_cost_per_successful_session"), run.get("label") or run["condition_profile_key"])


async def compare_runs(p: Principal, a: UUID, b: UUID) -> dict[str, Any]:
    """A = baseline, B = candidate. Comparing two targets is comparing two configurations, which is
    permitted when suite version, threshold version and metric definitions all match."""
    ra, side_a = await run_side(p, a)
    rb, side_b = await run_side(p, b)
    try:
        out = compare(side_a, side_b, ThresholdProfile.from_document(ra["threshold_document"]))
    except IncompatibleRuns as e:
        raise ApiError(409, e.code, str(e), extra={"a": e.a, "b": e.b}) from None
    names = {t["id"]: t["name"] for t in await repo.targets(p.workspace_id)}
    out["a"].update(target=names.get(ra["target_id"]), conditions=ra["condition_profile_key"], status=ra["status"])
    out["b"].update(target=names.get(rb["target_id"]), conditions=rb["condition_profile_key"], status=rb["status"])
    return out
