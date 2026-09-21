import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer

from app.catalog.read_service import CatalogReadService
from app.common.contracts import ErrorResponse
from app.knowledge.contracts import (
    KnowledgeDocument,
    KnowledgeDocumentInput,
    KnowledgeReviewInput,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.knowledge.service import KnowledgeService
from app.profiles.service import DomainError, ProfileService

admin_router = APIRouter(
    prefix="/api/v1/admin/knowledge",
    tags=["Reviewed knowledge"],
    dependencies=[Depends(HTTPBearer(auto_error=False))],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
    },
)
router = APIRouter(prefix="/api/v1/knowledge", tags=["Reviewed knowledge"])


async def admin_service_for(request: Request):
    deps, settings = request.app.state.dependencies, request.app.state.settings
    if (await deps.readiness()).status != "ready":
        raise DomainError(503, "DEPENDENCY_UNAVAILABLE", "知识库依赖暂不可用。")
    actor = request.state.admin_actor
    await asyncio.to_thread(ProfileService(deps.engine, settings).rate_limit, "admin:" + actor, 30)
    return KnowledgeService(deps.engine, CatalogReadService(deps.engine, settings), actor)


async def search_service_for(request: Request):
    deps, settings = request.app.state.dependencies, request.app.state.settings
    if (await deps.readiness()).status != "ready":
        raise DomainError(503, "DEPENDENCY_UNAVAILABLE", "知识库依赖暂不可用。")
    return KnowledgeService(deps.engine, CatalogReadService(deps.engine, settings))


AdminService = Annotated[KnowledgeService, Depends(admin_service_for)]
SearchService = Annotated[KnowledgeService, Depends(search_service_for)]


@admin_router.post(
    "/documents", response_model=KnowledgeDocument, operation_id="stage_knowledge_document"
)
async def stage(body: KnowledgeDocumentInput, service: AdminService):
    return await asyncio.to_thread(service.stage, body)


@admin_router.post(
    "/documents/{document_id}/review",
    response_model=KnowledgeDocument,
    operation_id="review_knowledge_document",
)
async def review(document_id: UUID, body: KnowledgeReviewInput, service: AdminService):
    return await asyncio.to_thread(service.review, document_id, body)


@router.post(
    "/search", response_model=KnowledgeSearchResponse, operation_id="search_reviewed_knowledge"
)
async def search(body: KnowledgeSearchRequest, service: SearchService):
    return await asyncio.to_thread(service.search, body)
