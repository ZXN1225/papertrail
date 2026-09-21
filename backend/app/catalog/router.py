import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.catalog.contracts import Category, Region
from app.catalog.read_contracts import (
    CatalogPage,
    OfferPage,
    PageSize,
    PriceQuote,
    PriceRequest,
    ProductDetail,
)
from app.catalog.read_service import CatalogReadService, PriceService
from app.common.contracts import ErrorResponse
from app.profiles.service import DomainError

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["Published catalog"],
    responses={code: {"model": ErrorResponse} for code in (404, 422, 503)},
)


async def service_for(request: Request):
    if (await request.app.state.dependencies.readiness()).status != "ready":
        raise DomainError(503, "DEPENDENCY_UNAVAILABLE", "目录暂时不可用。")
    return CatalogReadService(request.app.state.dependencies.engine, request.app.state.settings)


Service = Annotated[CatalogReadService, Depends(service_for)]


@router.get("/products", response_model=CatalogPage, operation_id="list_catalog_products")
async def products(
    service: Service,
    category: Category | None = None,
    region: Region | None = None,
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = Query(default=None, max_length=500),
    limit: PageSize = 20,
):
    return await asyncio.to_thread(service.list_products, category, region, q, cursor, limit)


@router.get("/products/{sku_id}", response_model=ProductDetail, operation_id="get_catalog_product")
async def product(sku_id: UUID, service: Service):
    return await asyncio.to_thread(service.product, sku_id)


@router.get(
    "/products/{sku_id}/offers", response_model=OfferPage, operation_id="list_catalog_offers"
)
async def offers(
    sku_id: UUID, service: Service, region: Region | None = None, include_historical: bool = False
):
    return await asyncio.to_thread(service.offers, sku_id, region, include_historical)


@router.post("/price-quotes", response_model=PriceQuote, operation_id="quote_catalog_prices")
async def quote(body: PriceRequest, service: Service):
    return await asyncio.to_thread(PriceService(service).quote, body)
