import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/backend";

export async function GET() {
  return forward("/api/v1/auth/me", { method: "GET" });
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ detail: "invalid_request" }, { status: 400 });
  }
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof (payload as { action?: unknown }).action !== "string"
  ) {
    return Response.json({ detail: "invalid_request" }, { status: 422 });
  }
  const { action, ...body } = payload as Record<string, unknown>;
  const routes: Record<string, string> = {
    register: "/api/v1/auth/register",
    login: "/api/v1/auth/login",
    logout: "/api/v1/auth/logout",
  };
  const path = routes[action as string];
  if (!path)
    return Response.json({ detail: "invalid_action" }, { status: 422 });
  return forward(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function forward(path: string, init: RequestInit) {
  const jar = await cookies();
  const token = jar.get("papertrail_session")?.value;
  try {
    const upstream = await backendRequest(path, {
      ...init,
      headers: {
        ...init.headers,
        ...(token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {}),
      },
    });
    const response = Response.json(await upstream.json().catch(() => ({})), {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) response.headers.set("Set-Cookie", setCookie);
    return response;
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}
