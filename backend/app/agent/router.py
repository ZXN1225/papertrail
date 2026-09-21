import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.agent.contracts import AgentPreviewRequest, AgentPreviewResponse
from app.agent.harness import AgentHarness
from app.agent.provider import DisabledProvider
from app.agent.tools import ToolRegistry
from app.catalog.read_service import CatalogReadService
from app.common.contracts import ErrorResponse
from app.knowledge.service import KnowledgeService
from app.profiles.router import Service as ProfileService

router = APIRouter(
    prefix="/api/v1/agent",
    tags=["Agent"],
    responses={code: {"model": ErrorResponse} for code in (403, 404, 409, 422, 429, 503)},
)


async def harness_for(request: Request, profile: ProfileService):
    catalog = CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    return AgentHarness(
        profile,
        ToolRegistry(catalog, KnowledgeService(request.app.state.dependencies.engine, catalog)),
        DisabledProvider(),
    )


Harness = Annotated[AgentHarness, Depends(harness_for)]


@router.post("/preview", response_model=AgentPreviewResponse, operation_id="preview_agent_run")
async def preview(body: AgentPreviewRequest, request: Request, harness: Harness):
    cookie = request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )
    return await asyncio.to_thread(harness.run, cookie, body)
