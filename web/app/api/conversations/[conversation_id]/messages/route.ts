import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/backend";

export async function GET(
  _request: Request,
  context: { params: Promise<{ conversation_id: string }> },
) {
  const { conversation_id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(conversation_id)) {
    return Response.json(
      { detail: "invalid_conversation_id" },
      { status: 422 },
    );
  }
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const response = await backendRequest(
      `/api/v1/conversations/${conversation_id}/messages`,
      {
        headers: token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {},
      },
    );
    return Response.json(await response.json().catch(() => ({})), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ conversation_id: string }> },
) {
  const { conversation_id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(conversation_id)) {
    return Response.json(
      { detail: "invalid_conversation_id" },
      { status: 422 },
    );
  }
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const response = await backendRequest(
      `/api/v1/conversations/${conversation_id}/messages`,
      {
        method: "DELETE",
        headers: token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {},
      },
    );
    return new Response(null, { status: response.status });
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}
