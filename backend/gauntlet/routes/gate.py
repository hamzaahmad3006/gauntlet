from fastapi import APIRouter, Depends

from gauntlet.controllers import gate_controller as ctl
from gauntlet.middleware.auth import Principal, rate_limit, require_scope
from gauntlet.schemas import GateRequest

router = APIRouter(prefix="/v1", tags=["gate"])


@router.post("/gate", summary="API-052 evaluate a gate")
async def gate(body: GateRequest, p: Principal = Depends(require_scope("gate:execute")),
               _: Principal = Depends(rate_limit("gate", 60, 3600))) -> dict:
    return await ctl.gate(p, body.run_id, body.baseline_run_id, body.tolerance)


@router.get("/gates", summary="Recent gate results")
async def history(p: Principal = Depends(require_scope("run:read"))) -> list:
    return await ctl.history(p)
