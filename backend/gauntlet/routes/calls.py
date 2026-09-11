from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response

from gauntlet.controllers import calls_controller as ctl
from gauntlet.middleware.auth import Principal, require_scope
from gauntlet.middleware.errors import not_found

router = APIRouter(prefix="/v1/calls", tags=["calls"])


@router.get("/{call_id}", summary="API-040 call detail: turns, events, transcript, verdict")
async def detail(call_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.detail(p, call_id)


@router.get("/{call_id}/audio", summary="Two-channel call audio (channel 0 caller, channel 1 agent)")
async def audio(call_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> Response:
    data, signed = await ctl.audio(p, call_id)
    if signed:
        return RedirectResponse(signed)
    if data is None:
        raise not_found("audio")
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "private, max-age=300"})


@router.get("/{call_id}/waveform", summary="Waveform peaks for both channels")
async def waveform(call_id: UUID, p: Principal = Depends(require_scope("run:read"))) -> dict:
    return await ctl.waveform(p, call_id)
