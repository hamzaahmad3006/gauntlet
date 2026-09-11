from uuid import UUID

from fastapi import APIRouter, Depends

from gauntlet.controllers import suites_controller as ctl
from gauntlet.middleware.auth import Principal, rate_limit, require_principal, require_user
from gauntlet.schemas import SuiteCreate

router = APIRouter(prefix="/v1", tags=["suites"])


@router.get("/suites", summary="API-021 list suites with scenarios and personas")
async def list_suites(p: Principal = Depends(require_principal)) -> list:
    return await ctl.list_suites(p)


@router.post("/suites", status_code=201, summary="API-020 create a suite version from YAML")
async def create(body: SuiteCreate, p: Principal = Depends(require_user),
                 _: Principal = Depends(rate_limit("suite_create", 30, 3600))) -> dict:
    return await ctl.create(p, body)


@router.get("/suites/{suite_id}", summary="Suite document and YAML source")
async def get_suite(suite_id: UUID, p: Principal = Depends(require_principal)) -> dict:
    return await ctl.get_suite(p, suite_id)


@router.get("/condition-profiles", summary="Condition profiles with every parameter")
async def condition_profiles(p: Principal = Depends(require_principal)) -> list:
    return await ctl.condition_profiles(p)


@router.get("/threshold-profiles", summary="API-022 threshold profiles")
async def threshold_profiles(p: Principal = Depends(require_principal)) -> list:
    return await ctl.threshold_profiles(p)
