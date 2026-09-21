from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class WriteProtection:
    """Validate before parsing; cap streamed bodies even without Content-Length."""

    def __init__(self, app, origins):
        self.app, self.origins = app, origins

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        private = path.startswith(("/api/v1/sessions", "/api/v1/profiles", "/api/v1/compatibility"))
        if scope["type"] != "http" or not private or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        error = None
        if (
            headers.get("origin") not in self.origins
            or headers.get("sec-fetch-site") == "cross-site"
        ):
            error = (403, "ORIGIN_REJECTED", "请求来源未获允许。")
        elif headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            error = (415, "JSON_REQUIRED", "请使用 JSON 提交需求。")
        body = bytearray()
        while error is None:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 16384:
                error = (413, "BODY_TOO_LARGE", "请求内容超过大小限制。")
            else:
                body.extend(chunk)
            if not message.get("more_body", False):
                break
        if error:
            status, code, text = error
            response = JSONResponse(
                status_code=status,
                content={
                    "error": {
                        "code": code,
                        "message": text,
                        "details": {},
                        "request_id": scope.get("state", {}).get("request_id", ""),
                    }
                },
            )
            return await response(scope, receive, send)
        supplied = False

        async def replay():
            nonlocal supplied
            if not supplied:
                supplied = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
