# ruff: noqa: E501
import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.catalog.read_service import CatalogReadService
from app.common.contracts import ErrorResponse
from app.profiles.router import Service as ProfileService
from app.profiles.service import DomainError
from app.recommendation.contracts import (
    ComparisonRequest,
    ComparisonResponse,
    LaptopRankRequest,
    LaptopRankResponse,
    PcSolveRequest,
    PcSolveResponse,
    RecommendationCreate,
    RecommendationRevisionCreate,
    RecommendationSnapshot,
)
from app.recommendation.pc_solver import PcSolver
from app.recommendation.service import LaptopRanker
from app.recommendation.snapshot_service import RecommendationSnapshotService

router = APIRouter(
    prefix="/api/v1/recommendations",
    tags=["Recommendations"],
    responses={code: {"model": ErrorResponse} for code in (422, 429, 503)},
)


async def ranker_for(request: Request, _: ProfileService):
    return LaptopRanker(
        CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    )


async def pc_solver_for(request: Request, _: ProfileService):
    return PcSolver(
        CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    )


async def snapshot_service_for(request: Request, profile: ProfileService):
    catalog = CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    return RecommendationSnapshotService(request.app.state.dependencies.engine, profile, catalog)


Ranker = Annotated[LaptopRanker, Depends(ranker_for)]
Solver = Annotated[PcSolver, Depends(pc_solver_for)]
SnapshotService = Annotated[RecommendationSnapshotService, Depends(snapshot_service_for)]


def require_idempotency_key(value: str | None):
    if value is None or not value.strip() or len(value) > 200:
        raise DomainError(
            422, "IDEMPOTENCY_KEY_REQUIRED", "请提供长度不超过 200 的 Idempotency-Key。"
        )
    return value


@router.post("/laptops", response_model=LaptopRankResponse, operation_id="rank_laptops")
async def laptops(body: LaptopRankRequest, ranker: Ranker):
    return await asyncio.to_thread(ranker.rank, body)


@router.post("/pc", response_model=PcSolveResponse, operation_id="solve_pc")
async def pc(body: PcSolveRequest, solver: Solver):
    return await asyncio.to_thread(solver.solve, body)


@router.post(
    "", response_model=RecommendationSnapshot, status_code=201, operation_id="create_recommendation"
)
async def create(
    body: RecommendationCreate,
    request: Request,
    service: SnapshotService,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await asyncio.to_thread(
        service.create,
        request.cookies.get(
            "__Host-computer_session"
            if request.app.state.settings.app_env == "production"
            else "computer_session"
        ),
        body,
        require_idempotency_key(idempotency_key),
    )


@router.post(
    "/comparisons", response_model=ComparisonResponse, operation_id="compare_recommendations"
)
async def compare(body: ComparisonRequest, request: Request, service: SnapshotService):
    cookie = request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )
    return await asyncio.to_thread(service.compare, cookie, body.recommendation_ids)


@router.get(
    "/{recommendation_id}", response_model=RecommendationSnapshot, operation_id="get_recommendation"
)
async def get(recommendation_id: UUID, request: Request, service: SnapshotService):
    cookie = request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )
    return await asyncio.to_thread(service.read, cookie, recommendation_id)


@router.post(
    "/{recommendation_id}/revisions",
    response_model=RecommendationSnapshot,
    status_code=201,
    operation_id="revise_recommendation",
)
async def revise(
    recommendation_id: UUID,
    body: RecommendationRevisionCreate,
    request: Request,
    service: SnapshotService,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    cookie = request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )
    return await asyncio.to_thread(
        service.revise, cookie, recommendation_id, body, require_idempotency_key(idempotency_key)
    )


@router.get("/{recommendation_id}/export", operation_id="export_recommendation")
async def export(recommendation_id: UUID, format: str, request: Request, service: SnapshotService):
    cookie = request.cookies.get(
        "__Host-computer_session"
        if request.app.state.settings.app_env == "production"
        else "computer_session"
    )
    if format not in {"json", "md"}:
        raise DomainError(422, "INVALID_EXPORT_FORMAT", "导出格式仅支持 json 或 md。")
    if format == "md":
        return PlainTextResponse(
            await asyncio.to_thread(service.markdown, cookie, recommendation_id)
        )
    return JSONResponse(await asyncio.to_thread(service.read, cookie, recommendation_id))
