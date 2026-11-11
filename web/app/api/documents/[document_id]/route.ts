import { cookies } from "next/headers";
import {
  backendRequest,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const UUID_PATTERN = /^[0-9a-f-]{36}$/i;

export async function GET(
  _request: Request,
  context: { params: Promise<{ document_id: string }> },
) {
  const { document_id } = await context.params;
  return proxy(document_id, { method: "GET" });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ document_id: string }> },
) {
  const { document_id } = await context.params;
  return proxy(document_id, { method: "DELETE" });
}

async function proxy(documentId: string, init: RequestInit) {
  if (!UUID_PATTERN.test(documentId)) {
    return Response.json(
      { detail: { code: "invalid_request", message: "文档编号无效。" } },
      { status: 422, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    const response = await backendRequest(`/api/v1/documents/${documentId}`, {
      ...init,
      headers: token
        ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
        : {},
    });
    if (response.status === 204) return new Response(null, { status: 204 });
    return await jsonResponse(response);
  } catch {
    return unavailableResponse();
  }
}
