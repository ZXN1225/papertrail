import hashlib
import hmac
import json

from pydantic import Field, ValidationError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.catalog.contracts import Digest, Nonempty
from app.common.contracts import Contract
from app.profiles.service import DomainError


class AdminConfig(Contract):
    operator_id: Nonempty = Field(max_length=120)
    token_sha256: Digest


def authenticate(settings, authorization):
    configured = settings.admin_auth_config.get_secret_value()
    if not configured:
        raise DomainError(503, "ADMIN_DISABLED", "管理员认证未配置，管理接口已禁用。")
    try:
        auth = AdminConfig.model_validate(json.loads(configured))
    except (ValidationError, ValueError):
        raise DomainError(503, "ADMIN_DISABLED", "管理员认证配置无效。") from None
    scheme, _, token = authorization.partition(" ")
    hashed = hashlib.sha256(token.encode()).hexdigest()
    if scheme != "Bearer" or len(token) < 32 or not hmac.compare_digest(hashed, auth.token_sha256):
        raise DomainError(401, "ADMIN_UNAUTHORIZED", "需要独立管理员凭据。")
    return auth.operator_id


class AdminProtection:
    """Authenticate before JSON parsing; Bearer credentials are never cookie-derived."""

    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/admin/"):
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        try:
            actor = authenticate(self.settings, headers.get("authorization", ""))
            origin = headers.get("origin")
            if origin is not None and origin not in set(
                self.settings.origins + [self.settings.public_base_url.rstrip("/")]
            ):
                raise DomainError(403, "ORIGIN_REJECTED", "请求来源未获允许。")
            if headers.get("sec-fetch-site") == "cross-site":
                raise DomainError(403, "ORIGIN_REJECTED", "请求来源未获允许。")
            scope.setdefault("state", {})["admin_actor"] = actor
            if scope["method"] in {"GET", "HEAD", "OPTIONS"}:
                return await self.app(scope, receive, send)
            if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                raise DomainError(415, "JSON_REQUIRED", "请使用 JSON 提交导入。")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 1048576:
                    raise DomainError(413, "BODY_TOO_LARGE", "导入请求上限为 1 MiB。")
                if not message.get("more_body", False):
                    break
        except DomainError as exc:
            return await JSONResponse(
                status_code=exc.status,
                content={
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": {},
                        "request_id": scope.get("state", {}).get("request_id", ""),
                    }
                },
            )(scope, receive, send)
        supplied = False

        async def replay():
            nonlocal supplied
            if not supplied:
                supplied = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
