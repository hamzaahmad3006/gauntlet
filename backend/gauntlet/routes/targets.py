from uuid import UUID

from fastapi import APIRouter, Depends

from gauntlet.controllers import targets_controller as ctl
from gauntlet.middleware.auth import Principal, rate_limit, require_principal, require_scope, require_user
from gauntlet.schemas import BaselinePromote, TargetCreate, TargetUpdate

router = APIRouter(prefix="/v1/targets", tags=["targets"])


@router.get("", summary="API-010 list targets (failures first)")
async def list_targets(p: Principal = Depends(require_principal)) -> list:
    return await ctl.list_targets(p)


@router.post("", status_code=201, summary="API-011 register a target")
async def create(body: TargetCreate, p: Principal = Depends(require_user),
                 _: Principal = Depends(rate_limit("target_create", 30, 3600))) -> dict:
    return await ctl.create(p, body)


@router.get("/{target_id}", summary="Target detail")
async def get_target(target_id: UUID, p: Principal = Depends(require_principal)) -> dict:
    return await ctl.get_target(p, target_id)


@router.patch("/{target_id}", summary="API-014 update a target (connection change revokes verification)")
async def update(target_id: UUID, body: TargetUpdate, p: Principal = Depends(require_user)) -> dict:
    return await ctl.update(p, target_id, body)


@router.post("/{target_id}/verify", summary="API-012 verify ownership")
async def verify(target_id: UUID, p: Principal = Depends(require_user),
                 _: Principal = Depends(rate_limit("verify", 20, 3600))) -> dict:
    return await ctl.verify(p, target_id)


@router.post("/{target_id}/diagnose", summary="API-013 single-call connectivity check")
async def diagnose(target_id: UUID, p: Principal = Depends(require_user),
                   _: Principal = Depends(rate_limit("diagnose", 20, 3600))) -> dict:
    return await ctl.diagnose(p, target_id)


@router.post("/{target_id}/baseline", summary="API-051 promote a run to baseline")
async def baseline(target_id: UUID, body: BaselinePromote, p: Principal = Depends(require_scope("gate:execute"))) -> dict:
    return await ctl.promote_baseline(p, target_id, body.run_id)
