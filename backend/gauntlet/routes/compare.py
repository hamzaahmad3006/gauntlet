from uuid import UUID

from fastapi import APIRouter, Depends

from gauntlet.controllers import compare_controller as ctl
from gauntlet.middleware.auth import Principal, require_scope

router = APIRouter(prefix="/v1", tags=["compare"])


@router.get("/compare", summary="API-050 compare two runs (a = baseline, b = candidate)")
async def compare(a: UUID, b: UUID, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.compare_runs(p, a, b)
