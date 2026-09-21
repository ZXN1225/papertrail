import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from sqlalchemy.exc import SQLAlchemyError

from app.catalog.contracts import RECORD_MODELS
from app.catalog.read_service import CatalogReadService
from app.catalog.router import router as catalog_router
from app.common.config import Settings
from app.common.contracts import ErrorResponse, LiveResponse, PlatformStatus, ReadyResponse
from app.common.dependencies import Dependencies
from app.compatibility.router import router as compatibility_router
from app.ingestion.auth import AdminProtection
from app.ingestion.router import router as import_router
from app.profiles.protection import WriteProtection
from app.profiles.router import router as profile_router
from app.profiles.service import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.dependencies = Dependencies(settings)
        try:
            yield
        finally:
            await app.state.dependencies.close()

    app = FastAPI(title="电脑推荐平台 API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    base_openapi = app.openapi

    def record_openapi():
        schema = base_openapi()
        _, definitions = models_json_schema(
            [(model, "validation") for model in RECORD_MODELS],
            ref_template="#/components/schemas/{model}",
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(definitions["$defs"])
        return schema

    app.openapi = record_openapi
    app.include_router(profile_router)
    app.include_router(import_router)
    app.include_router(catalog_router)
    app.include_router(compatibility_router)
    app.add_middleware(AdminProtection, settings=settings)
    app.add_middleware(
        WriteProtection, origins=set(settings.origins + [settings.public_base_url.rstrip("/")])
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        headers = {"Retry-After": exc.details["retry_after"]} if exc.status == 429 else {}
        return JSONResponse(
            status_code=exc.status,
            headers=headers,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return await domain_error(
            request, DomainError(422, "INVALID_REQUEST", "请求字段无效，请检查需求内容。")
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request: Request, exc: SQLAlchemyError):
        return await domain_error(
            request, DomainError(503, "DEPENDENCY_UNAVAILABLE", "暂时无法读取或保存，请稍后重试。")
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logging.getLogger("app").error(
            "request_failed request_id=%s type=%s", request_id, type(exc).__name__
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务暂时不可用，请稍后重试。",
                    "details": {},
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    @app.get("/api/v1/health/live", response_model=LiveResponse, operation_id="get_liveness")
    async def live():
        return LiveResponse()

    @app.get(
        "/api/v1/health/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ReadyResponse}},
        operation_id="get_readiness",
    )
    async def ready(request: Request, response: Response):
        result = await request.app.state.dependencies.readiness()
        response.status_code = 200 if result.status == "ready" else 503
        return result

    @app.get(
        "/api/v1/platform/status",
        response_model=PlatformStatus,
        responses={503: {"model": ErrorResponse}},
        operation_id="get_platform_status",
    )
    async def platform_status(request: Request):
        result = await request.app.state.dependencies.readiness()
        if result.status != "ready":
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "DEPENDENCY_UNAVAILABLE",
                        "message": "服务暂时无法连接，请稍后重试。",
                        "details": {},
                        "request_id": request.state.request_id,
                    }
                },
            )
        catalog = CatalogReadService(
            request.app.state.dependencies.engine, request.app.state.settings
        )
        version = await asyncio.to_thread(catalog.current_version)
        return PlatformStatus(data_status="published" if version else "empty", data_version=version)

    return app
