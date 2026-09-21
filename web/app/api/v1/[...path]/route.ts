// Fixed application routes only; browser input cannot select a host or arbitrary URL.
const uuid = "[0-9a-fA-F-]{36}";
const allowed = new Map([
  [
    "GET",
    new RegExp(
      `^(sessions/current|profiles/${uuid}(/revisions/[0-9]+)?|catalog/products(/${uuid}(/offers)?)?|agent/runs/${uuid}(/events)?)$`,
    ),
  ],
  [
    "POST",
    new RegExp(
      `^(sessions|sessions/reset|profiles|catalog/price-quotes|agent/sessions|agent/sessions/${uuid}/runs|agent/runs/${uuid}/cancel)$`,
    ),
  ],
  ["PATCH", new RegExp(`^profiles/${uuid}$`)],
  ["DELETE", new RegExp(`^(sessions/current|agent/sessions/${uuid})$`)],
]);

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  const requestId = crypto.randomUUID();
  function error(status: number, message: string) {
    return Response.json(
      {
        error: {
          code: status === 413 ? "BODY_TOO_LARGE" : "DEPENDENCY_UNAVAILABLE",
          message,
          details: {},
          request_id: requestId,
        },
      },
      {
        status,
        headers: { "Cache-Control": "no-store", "X-Request-ID": requestId },
      },
    );
  }
  if (!allowed.get(request.method)?.test(path))
    return new Response(null, { status: 404 });
  const headers = new Headers();
  for (const key of [
    "cookie",
    "origin",
    "content-type",
    "x-csrf-token",
    "last-event-id",
    "sec-fetch-site",
  ]) {
    const value = request.headers.get(key);
    if (value !== null) headers.set(key, value);
  }
  let body: Uint8Array | undefined;
  if (request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const item = await reader.read();
      if (item.done) break;
      size += item.value.length;
      if (size > 16384) {
        await reader.cancel();
        return error(413, "请求内容超过大小限制。");
      }
      chunks.push(item.value);
    }
    body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.length;
    }
  }
  try {
    const origin = process.env.API_BASE_URL || "http://127.0.0.1:8000";
    const upstream = await fetch(new URL(`/api/v1/${path}`, origin), {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const key of ["content-type", "x-request-id", "retry-after"]) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      responseHeaders.append("set-cookie", cookie);
    return new Response(upstream.status === 204 ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return error(
      503,
      "服务暂时无法连接，保存结果尚未确认，请重新读取后再操作。",
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
