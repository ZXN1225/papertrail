import { cookies } from "next/headers";
import { backendRequest } from "@/lib/api/backend";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ conversation_id: string }> },
) {
  const { conversation_id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(conversation_id)) {
    return Response.json(
      { detail: "invalid_conversation_id" },
      { status: 422 },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "invalid_request" }, { status: 400 });
  }
  if (
    !body ||
    typeof body !== "object" ||
    typeof (body as { title?: unknown }).title !== "string" ||
    !(body as { title: string }).title.trim() ||
    (body as { title: string }).title.length > 120
  ) {
    return Response.json(
      { detail: "invalid_conversation_title" },
      { status: 422 },
    );
  }
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const response = await backendRequest(
      `/api/v1/conversations/${conversation_id}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token
            ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
            : {}),
        },
        body: JSON.stringify({
          title: (body as { title: string }).title.trim(),
        }),
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
      `/api/v1/conversations/${conversation_id}`,
      {
        method: "DELETE",
        headers: token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : undefined,
      },
    );
    if (response.status === 204) {
      return new Response(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
    }
    return Response.json(await response.json().catch(() => ({})), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "backend_unavailable" }, { status: 503 });
  }
}
