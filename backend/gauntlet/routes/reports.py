from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from gauntlet.context import ctx
from gauntlet.controllers import reports_controller as ctl
from gauntlet.middleware.auth import Principal, require_scope, require_user
from gauntlet.middleware.errors import ApiError
from gauntlet.schemas import ShareCreate

router = APIRouter(tags=["reports"])


@router.get("/v1/runs/{run_id}/report", summary="API-041 rendered report (HTML)", response_class=HTMLResponse)
async def report_html(run_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> HTMLResponse:
    return HTMLResponse(await ctl.report(p, run_id, "html"))


@router.get("/v1/runs/{run_id}/report.json", summary="Report data for the dashboard")
async def report_json(run_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.report(p, run_id, "json")


@router.get("/v1/runs/{run_id}/report.md", summary="API-043 Markdown export", response_class=PlainTextResponse)
async def report_md(run_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> PlainTextResponse:
    return PlainTextResponse(await ctl.report(p, run_id, "md"), media_type="text/markdown")


@router.post("/v1/runs/{run_id}/share", status_code=201, summary="API-042 create a share link")
async def share(run_id: UUID, body: ShareCreate, p: Principal = Depends(require_user)) -> dict:
    return await ctl.share(p, run_id, body.expires_in_days)


@router.delete("/v1/runs/{run_id}/share", summary="Revoke every share link for a run")
async def revoke(run_id: UUID, p: Principal = Depends(require_user)) -> dict:
    return await ctl.revoke_share(p, run_id)


async def _public_limit(request: Request) -> None:
    addr = request.client.host if request.client else "unknown"
    ok, _, _ = await ctx().broker.hit(f"public:{addr}", 30, 60)
    if not ok:
        raise ApiError(429, "rate_limited", "Too many requests; try again in a minute.", headers={"Retry-After": "60"})


@router.get("/public/reports/{token}", summary="API-044 public read-only report", response_class=HTMLResponse,
            dependencies=[Depends(_public_limit)])
async def public_html(token: str) -> HTMLResponse:
    return HTMLResponse(await ctl.public_report(token, "html"))


@router.get("/public/reports/{token}.json", summary="Public report data", dependencies=[Depends(_public_limit)])
async def public_json(token: str) -> dict:
    return await ctl.public_report(token, "json")
