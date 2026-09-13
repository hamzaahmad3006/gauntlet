from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse

from gauntlet.controllers import system_controller as ctl
from gauntlet.middleware.auth import Principal, require_principal

router = APIRouter()


@router.get("/healthz", summary="API-070 liveness")
async def healthz() -> dict:
    return ctl.healthz()


@router.get("/readyz", summary="API-071 dependency readiness")
async def readyz() -> JSONResponse:
    body, ok = await ctl.readyz()
    return JSONResponse(body, status_code=200 if ok else 503)


@router.get("/v1/me", summary="API-001 current principal and workspace")
async def me(p: Principal = Depends(require_principal)) -> dict:
    return await ctl.me(p)


@router.get("/v1/system", summary="Provider status, metric definitions and disclosures (public)")
async def system() -> dict:
    return ctl.system()


@router.get("/v1/calibration", summary="API-060 rig error bound and method (public)")
async def calibration() -> dict:
    return ctl.calibration()


@router.get("/metrics", summary="Operational metrics for GAUNTLET itself (Prometheus text format)",
            response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(await ctl.prometheus(), media_type="text/plain; version=0.0.4")
