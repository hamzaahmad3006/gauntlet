from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from gauntlet.controllers import runs_controller as ctl
from gauntlet.middleware.auth import Principal, rate_limit, require_scope, require_user
from gauntlet.schemas import ConditionChange, RunCreate

router = APIRouter(prefix="/v1/runs", tags=["runs"])


@router.post("", status_code=201, summary="API-030 create a run")
async def create(body: RunCreate, idempotency_key: str | None = Header(default=None),
                 p: Principal = Depends(require_scope("run:create")),
                 _: Principal = Depends(rate_limit("run_create", 20, 3600))) -> dict:
    return await ctl.create(p, body, idempotency_key)


@router.post("/estimate", summary="API-031 pre-run estimate (no side effects)")
async def estimate(body: RunCreate, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.estimate(p, body)


@router.get("", summary="API-032 list runs, newest first")
async def list_runs(target_id: UUID | None = None, status: str | None = None,
                    limit: int = Query(default=25, ge=1, le=100), cursor: str | None = None,
                    p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.list_runs(p, target_id, status, limit, cursor)


@router.get("/{run_id}", summary="API-036 run summary with metrics, score and cost")
async def summary(run_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.summary(p, run_id)


@router.post("/{run_id}/abort", summary="API-033 abort a run")
async def abort(run_id: UUID, p: Principal = Depends(require_scope("run:create"))) -> dict:
    return await ctl.abort(p, run_id)


@router.post("/{run_id}/conditions", summary="API-035 mid-run condition injection")
async def conditions(run_id: UUID, body: ConditionChange, p: Principal = Depends(require_user),
                     _: Principal = Depends(rate_limit("conditions", 30, 3600))) -> dict:
    return await ctl.inject_conditions(p, run_id, body)


@router.get("/{run_id}/events", summary="API-034 live event stream (SSE)")
async def events(run_id: UUID, last_event_id: str | None = Header(default=None),
                 p: Principal = Depends(require_scope("run:read"))) -> StreamingResponse:
    stream = await ctl.event_stream(p, run_id, last_event_id)
    return StreamingResponse(stream, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
