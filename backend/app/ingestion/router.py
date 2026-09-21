import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer

from app.common.contracts import ErrorResponse
from app.ingestion.contracts import (
    ImportInput,
    ImportJob,
    Preview,
    Published,
    PublishInput,
    ReviewInput,
)
from app.ingestion.service import ImportService
from app.profiles.service import DomainError, ProfileService

router = APIRouter(
    prefix="/api/v1/admin/imports",
    tags=["Manual imports"],
    dependencies=[Depends(HTTPBearer(auto_error=False))],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
    },
)


async def service_for(request: Request):
    deps, settings = request.app.state.dependencies, request.app.state.settings
    if (await deps.readiness()).status != "ready":
        raise DomainError(503, "DEPENDENCY_UNAVAILABLE", "导入依赖暂不可用。")
    actor = request.state.admin_actor
    if request.method != "GET":
        await asyncio.to_thread(
            ProfileService(deps.engine, settings).rate_limit, "admin:" + actor, 30
        )
    return ImportService(deps.engine, settings, actor)


Service = Annotated[ImportService, Depends(service_for)]


@router.post("/preview", response_model=Preview, operation_id="preview_manual_import")
async def preview(body: ImportInput, service: Service):
    return await asyncio.to_thread(service.preview, body)


@router.post("", response_model=ImportJob, operation_id="stage_manual_import")
async def stage(body: ImportInput, service: Service):
    return await asyncio.to_thread(service.stage, body)


@router.get("/{job_id}", response_model=ImportJob, operation_id="get_manual_import")
async def get(job_id: UUID, service: Service):
    return await asyncio.to_thread(service.get, job_id)


@router.post("/{job_id}/review", response_model=ImportJob, operation_id="review_manual_import")
async def review(job_id: UUID, body: ReviewInput, service: Service):
    return await asyncio.to_thread(service.review, job_id, body)


@router.post("/{job_id}/publish", response_model=Published, operation_id="publish_manual_import")
async def publish(job_id: UUID, body: PublishInput, service: Service):
    return await asyncio.to_thread(service.publish, job_id, body)
