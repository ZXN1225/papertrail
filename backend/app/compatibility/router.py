import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.catalog.read_service import CatalogReadService
from app.common.contracts import ErrorResponse
from app.compatibility.contracts import CompatibilityReport, CompatibilityRequest
from app.compatibility.service import CompatibilityService
from app.profiles.router import Service as ProfileService

router = APIRouter(
    prefix="/api/v1/compatibility",
    tags=["Compatibility"],
    responses={code: {"model": ErrorResponse} for code in (404, 422, 429, 503)},
)


async def service_for(request: Request, _: ProfileService):
    return CompatibilityService(
        CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    )


Service = Annotated[CompatibilityService, Depends(service_for)]


@router.post("/check", response_model=CompatibilityReport, operation_id="check_compatibility")
async def check(body: CompatibilityRequest, service: Service):
    return await asyncio.to_thread(service.check, body)
