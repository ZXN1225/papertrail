# ruff: noqa: E501
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.catalog.read_service import CatalogReadService
from app.common.contracts import ErrorResponse
from app.profiles.router import Service as ProfileService
from app.recommendation.contracts import LaptopRankRequest, LaptopRankResponse
from app.recommendation.service import LaptopRanker

router = APIRouter(
    prefix="/api/v1/recommendations",
    tags=["Recommendations"],
    responses={code: {"model": ErrorResponse} for code in (422, 429, 503)},
)


async def ranker_for(request: Request, _: ProfileService):
    return LaptopRanker(
        CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)
    )


Ranker = Annotated[LaptopRanker, Depends(ranker_for)]


@router.post("/laptops", response_model=LaptopRankResponse, operation_id="rank_laptops")
async def laptops(body: LaptopRankRequest, ranker: Ranker):
    return await asyncio.to_thread(ranker.rank, body)
