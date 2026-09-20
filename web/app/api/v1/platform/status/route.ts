// A single read-only development bridge. No arbitrary URL proxy or credentials in the browser.
export const dynamic = "force-dynamic";

export async function GET() {
  const origin = process.env.API_BASE_URL || "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(new URL("/api/v1/platform/status", origin), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      redirect: "error",
    });
    if (!upstream.ok) throw new Error("API unavailable");
    const body = await upstream.json();
    return Response.json(body, { headers: { "Cache-Control": "no-store" } });
  } catch {
    const requestId = crypto.randomUUID();
    return Response.json(
      {
        error: {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时无法连接，请稍后重试。",
          details: {},
          request_id: requestId,
        },
      },
      {
        status: 503,
        headers: { "Cache-Control": "no-store", "X-Request-ID": requestId },
      },
    );
  }
}
