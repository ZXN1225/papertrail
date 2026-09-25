const DEFAULT_API_BASE_URL = "http://127.0.0.1:8001";
const MAX_RESPONSE_BYTES = 4_000_000;

function apiBaseUrl(): string {
  const raw = process.env.PAPERTRAIL_API_BASE_URL || DEFAULT_API_BASE_URL;
  const url = new URL(raw);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error("invalid_backend_configuration");
  }
  return url.toString().replace(/\/$/, "");
}

export async function backendRequest(
  path: string,
  init?: RequestInit,
  timeoutMs = 15_000,
): Promise<Response> {
  try {
    return await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("backend_unavailable");
  }
}

export async function jsonResponse(upstream: Response): Promise<Response> {
  const bytes = new Uint8Array(await upstream.arrayBuffer());
  if (bytes.byteLength > MAX_RESPONSE_BYTES) {
    return Response.json(
      {
        detail: {
          code: "response_too_large",
          message: "上游响应超过显示上限。",
        },
      },
      { status: 502 },
    );
  }
  try {
    const value: unknown = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(bytes),
    );
    return Response.json(value, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      {
        detail: {
          code: "invalid_backend_response",
          message: "研究服务返回了无法识别的数据。",
        },
      },
      { status: 502 },
    );
  }
}

export function unavailableResponse(): Response {
  return Response.json(
    {
      detail: {
        code: "backend_unavailable",
        message: "研究服务暂时无法连接，请检查后端并重试。",
      },
    },
    { status: 503, headers: { "Cache-Control": "no-store" } },
  );
}

export function invalidResponse(message: string): Response {
  return Response.json(
    { detail: { code: "invalid_request", message } },
    { status: 422, headers: { "Cache-Control": "no-store" } },
  );
}

export function tooLargeResponse(): Response {
  return Response.json(
    {
      detail: {
        code: "request_too_large",
        message: "请求内容超过允许大小。",
      },
    },
    { status: 413, headers: { "Cache-Control": "no-store" } },
  );
}
