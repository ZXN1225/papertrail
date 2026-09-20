import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.config import Settings
from app.common.contracts import ErrorResponse, LiveResponse, PlatformStatus, ReadyResponse
from app.common.dependencies import Dependencies


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

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
        # Catalog schema/imports arrive in T02-T04. This describes capability, not catalog counts.
        return PlatformStatus()

    return app
