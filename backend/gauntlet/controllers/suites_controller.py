"""Suites, condition profiles, threshold profiles (SRS-FR-020..023, -050, -090; API-020..022)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from gauntlet.controllers.serialize import jsonable
from gauntlet.db import repo
from gauntlet.db import tables as T
from gauntlet.db.seed import insert_suite
from gauntlet.media.chaos import ChaosParams
from gauntlet.middleware.auth import Principal
from gauntlet.middleware.errors import ApiError, conflict, not_found
from gauntlet.schemas import SuiteCreate
from gauntlet.suites.loader import SuiteValidationError, load_suite_text


async def list_suites(p: Principal) -> list[dict[str, Any]]:
    out = []
    for s in await repo.suites(p.workspace_id):
        doc = s["document"]
        out.append({"id": str(s["id"]), "key": s["key"], "name": s["name"], "version_hash": s["version_hash"],
                    "parent_suite_id": jsonable(s["parent_suite_id"]), "created_at": jsonable(s["created_at"]),
                    "scenarios": doc.get("scenarios", []), "personas": doc.get("personas", []),
                    "domain": doc.get("domain"), "description": doc.get("description")})
    return out


async def get_suite(p: Principal, suite_id: UUID) -> dict[str, Any]:
    row = await repo.one(T.suites, p.workspace_id, suite_id)
    if row is None:
        raise not_found("suite")
    return {"id": str(row["id"]), "key": row["key"], "name": row["name"], "version_hash": row["version_hash"],
            "document": row["document"], "yaml_source": row["yaml_source"]}


async def create(p: Principal, body: SuiteCreate) -> dict[str, Any]:
    try:
        suite = load_suite_text(body.yaml)
    except SuiteValidationError as e:
        raise ApiError(422, "validation_failed", e.message, e.pointer or None,
                       extra={"line": e.line, "column": e.column}) from None
    parent = next((s["id"] for s in await repo.suites(p.workspace_id) if s["key"] == suite.key), None)
    try:
        async with repo.tx() as c:
            sid = await insert_suite(c, p.workspace_id, suite, body.yaml, parent)
            await repo.audit(c, p.workspace_id, p.actor, "suite.created", f"suite:{sid}", {"hash": suite.version_hash})
    except IntegrityError:
        raise conflict("suite_exists", "an identical suite version already exists",
                       version_hash=suite.version_hash) from None
    return {"suite": {"id": str(sid), "key": suite.key, "name": suite.name}, "version_hash": suite.version_hash}


async def condition_profiles(p: Principal) -> list[dict[str, Any]]:
    out = []
    for r in await repo.condition_profiles(p.workspace_id):
        params = ChaosParams.from_profile(r["parameters"], strict=False)
        out.append({"key": r["key"], "parameters": r["parameters"], "active": params.active,
                    "interruptions_per_call": params.interruptions_per_call})
    order = ["clean", "mobile", "hostile", "turn_taking"]
    out.sort(key=lambda x: order.index(x["key"]) if x["key"] in order else 99)
    return out


async def threshold_profiles(p: Principal) -> list[dict[str, Any]]:
    return [{"key": r["key"], "version_hash": r["version_hash"], "document": r["document"],
             "created_at": jsonable(r["created_at"])} for r in await repo.threshold_profiles(p.workspace_id)]
