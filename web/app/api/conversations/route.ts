import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/backend";

export async function GET() {
  return proxy("GET");
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "invalid_request" }, { status: 400 });
  }
  if (
    !body ||
    typeof body !== "object" ||
    typeof (body as { title?: unknown }).title !== "string"
  ) {
    return Response.json({ detail: "invalid_request" }, { status: 422 });
  }
  return proxy("POST", JSON.stringify(body));
}

async function proxy(method: "GET" | "POST", body?: string) {
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const headers = new Headers(
      body ? { "Content-Type": "application/json" } : undefined,
    );
    if (token)
      headers.set("Cookie", `papertrail_session=${encodeURIComponent(token)}`);
    const response = await backendRequest("/api/v1/conversations", {
      method,
      ...(body
        ? { body, headers: { "Content-Type": "application/json" } }
        : {}),
      headers,
    });
    return Response.json(await response.json().catch(() => ({})), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}
