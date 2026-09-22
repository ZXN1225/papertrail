import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse

from app.agent.contracts import (
    AgentPreviewRequest,
    AgentPreviewResponse,
    AgentRun,
    AgentRunCreate,
    AgentSession,
)
from app.agent.harness import AgentHarness
from app.agent.provider import DisabledProvider, OpenAIProvider
from app.agent.run_service import AgentRunService
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
    settings = request.app.state.settings
    provider = DisabledProvider()
    if settings.llm_provider == "openai":
        provider = OpenAIProvider(
            settings.llm_api_key.get_secret_value(),
            settings.llm_model,
            settings.llm_base_url,
            settings.llm_timeout_seconds,
            settings.llm_max_output_tokens,
        )
    return AgentHarness(
        profile,
        ToolRegistry(catalog, KnowledgeService(request.app.state.dependencies.engine, catalog)),
        provider,
    )


Harness = Annotated[AgentHarness, Depends(harness_for)]


async def run_service_for(request: Request, profile: ProfileService, harness: Harness):
    return AgentRunService(request.app.state.dependencies.engine, profile, harness)


RunService = Annotated[AgentRunService, Depends(run_service_for)]


def cookie_for(request):
    return request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )


@router.post("/preview", response_model=AgentPreviewResponse, operation_id="preview_agent_run")
async def preview(body: AgentPreviewRequest, request: Request, harness: Harness):
    return await asyncio.to_thread(harness.run, cookie_for(request), body)


@router.post(
    "/sessions", response_model=AgentSession, status_code=201, operation_id="create_agent_session"
)
async def create_session(request: Request, service: RunService):
    return await asyncio.to_thread(service.create_session, cookie_for(request))


@router.post(
    "/sessions/{agent_session_id}/runs",
    response_model=AgentRun,
    status_code=202,
    operation_id="create_agent_run",
)
async def create_run(
    agent_session_id: UUID, body: AgentRunCreate, request: Request, service: RunService
):
    return await asyncio.to_thread(service.create_run, cookie_for(request), agent_session_id, body)


@router.get("/runs/{run_id}", response_model=AgentRun, operation_id="get_agent_run")
async def get_run(run_id: UUID, request: Request, service: RunService):
    return await asyncio.to_thread(service.read_run, cookie_for(request), run_id)


@router.get("/runs/{run_id}/events", operation_id="stream_agent_run_events")
async def stream_events(
    run_id: UUID,
    request: Request,
    service: RunService,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    try:
        after = int(last_event_id or "0")
    except ValueError as exc:
        from app.profiles.service import DomainError

        raise DomainError(422, "INVALID_LAST_EVENT_ID", "Last-Event-ID 必须为正整数。") from exc
    if after < 0:
        from app.profiles.service import DomainError

        raise DomainError(422, "INVALID_LAST_EVENT_ID", "Last-Event-ID 必须为正整数。")
    events = await asyncio.to_thread(service.events, cookie_for(request), run_id, after)

    async def body():
        if not events:
            yield ": keepalive\n\n"
        for event in events:
            yield (
                f"id: {event.event_id}\n"
                f"event: {event.type}\n"
                f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel", response_model=AgentRun, operation_id="cancel_agent_run")
async def cancel_run(run_id: UUID, request: Request, service: RunService):
    return await asyncio.to_thread(service.cancel, cookie_for(request), run_id)


@router.delete("/sessions/{agent_session_id}", status_code=204, operation_id="delete_agent_session")
async def delete_session(agent_session_id: UUID, request: Request, service: RunService):
    await asyncio.to_thread(service.delete_session, cookie_for(request), agent_session_id)
    return Response(status_code=204)
