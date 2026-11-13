import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/backend";

export async function GET() {
  return proxy("/api/v1/library", { method: "GET" });
}

export async function POST(request: Request) {
  const body = await request.text();
  if (body.length > 24_576)
    return Response.json({ detail: "request_too_large" }, { status: 413 });
  return proxy("/api/v1/library", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function proxy(path: string, init: RequestInit) {
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const response = await backendRequest(path, {
      ...init,
      headers: {
        ...init.headers,
        ...(token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {}),
      },
    });
    if (response.status === 204) return new Response(null, { status: 204 });
    return Response.json(await response.json().catch(() => ({})), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}
