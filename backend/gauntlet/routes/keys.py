from uuid import UUID

from fastapi import APIRouter, Depends, Response

from gauntlet.controllers import keys_controller as ctl
from gauntlet.middleware.auth import Principal, rate_limit, require_user
from gauntlet.schemas import ApiKeyCreate

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.post("", status_code=201, summary="API-002 create an API key (shown once)")
async def create(body: ApiKeyCreate, p: Principal = Depends(require_user),
                 _: Principal = Depends(rate_limit("key_create", 10, 3600))) -> dict:
    return await ctl.create(p, body)


@router.get("", summary="API-003 list API keys")
async def list_keys(p: Principal = Depends(require_user)) -> list:
    return await ctl.list_keys(p)


@router.delete("/{key_id}", status_code=204, summary="API-004 revoke an API key")
async def revoke(key_id: UUID, p: Principal = Depends(require_user)) -> Response:
    await ctl.revoke(p, key_id)
    return Response(status_code=204)
