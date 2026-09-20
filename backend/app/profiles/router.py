import asyncio
import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.common.contracts import ErrorResponse
from app.profiles.contracts import (
    EmptyRequest,
    PatchRequest,
    ProfileInput,
    ProfileSnapshot,
    SessionResponse,
)
from app.profiles.service import DomainError, ProfileService

router = APIRouter(
    prefix="/api/v1",
    responses={
        status: {"model": ErrorResponse} for status in (403, 404, 409, 413, 415, 422, 429, 503)
    },
)


def cookie_name(settings):
    return "__Host-computer_session" if settings.app_env == "production" else "computer_session"


def cookie_value(request):
    return request.cookies.get(cookie_name(request.app.state.settings))


def set_cookie(response, cookie, settings):
    response.set_cookie(
        cookie_name(settings),
        cookie,
        max_age=86400,
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )


async def service_for(request: Request):
    settings = request.app.state.settings
    deps = request.app.state.dependencies
    if (
        len(settings.session_signing_secret.get_secret_value()) < 32
        or (await deps.readiness()).status != "ready"
    ):
        raise DomainError(503, "DEPENDENCY_UNAVAILABLE", "暂时无法保存或读取需求，请稍后重试。")
    service = ProfileService(deps.engine, settings)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        peer = request.client.host if request.client else "unknown"
        await asyncio.to_thread(
            service.rate_limit, "peer:" + peer, settings.session_write_limit * 5
        )
        if request.url.path == "/api/v1/sessions":
            await asyncio.to_thread(
                service.rate_limit, "bootstrap:" + peer, settings.session_write_limit * 2
            )
        else:
            cookie = cookie_value(request)
            await asyncio.to_thread(service.current, cookie)
            token = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(token.encode(), service.csrf(cookie).encode()):
                raise DomainError(403, "CSRF_REJECTED", "请求校验失败，请重新加载页面。")
            await asyncio.to_thread(
                service.rate_limit,
                "session:" + service.identity(cookie),
                settings.session_write_limit,
            )
    return service


Service = Annotated[ProfileService, Depends(service_for)]


@router.post("/sessions", response_model=SessionResponse, operation_id="bootstrap_session")
async def bootstrap(body: EmptyRequest, request: Request, response: Response, service: Service):
    result, cookie = await asyncio.to_thread(service.bootstrap, cookie_value(request))
    if cookie:
        set_cookie(response, cookie, request.app.state.settings)
    return result


@router.get("/sessions/current", response_model=SessionResponse, operation_id="get_current_session")
async def current(request: Request, service: Service):
    return await asyncio.to_thread(service.current, cookie_value(request))


@router.post("/sessions/reset", response_model=SessionResponse, operation_id="reset_session")
async def reset(body: EmptyRequest, request: Request, response: Response, service: Service):
    result, cookie = await asyncio.to_thread(service.reset, cookie_value(request))
    set_cookie(response, cookie, request.app.state.settings)
    return result


@router.delete("/sessions/current", status_code=204, operation_id="delete_current_session")
async def remove(body: EmptyRequest, request: Request, service: Service):
    await asyncio.to_thread(service.remove, cookie_value(request))
    settings = request.app.state.settings
    response = Response(status_code=204)
    response.delete_cookie(
        cookie_name(settings),
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    return response


@router.post(
    "/profiles", response_model=ProfileSnapshot, status_code=201, operation_id="create_profile"
)
async def create_profile(body: ProfileInput, request: Request, service: Service):
    return await asyncio.to_thread(service.save, cookie_value(request), body)


@router.get("/profiles/{profile_id}", response_model=ProfileSnapshot, operation_id="get_profile")
async def get_profile(profile_id: UUID, request: Request, service: Service):
    return await asyncio.to_thread(service.read, cookie_value(request), profile_id)


@router.get(
    "/profiles/{profile_id}/revisions/{revision}",
    response_model=ProfileSnapshot,
    operation_id="get_profile_revision",
)
async def get_revision(profile_id: UUID, revision: int, request: Request, service: Service):
    return await asyncio.to_thread(service.read, cookie_value(request), profile_id, revision)


@router.patch(
    "/profiles/{profile_id}", response_model=ProfileSnapshot, operation_id="patch_profile"
)
async def patch_profile(profile_id: UUID, body: PatchRequest, request: Request, service: Service):
    return await asyncio.to_thread(
        service.save, cookie_value(request), body.patch, profile_id, body.expected_revision
    )
