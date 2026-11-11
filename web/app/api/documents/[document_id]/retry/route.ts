import { cookies } from "next/headers";
import {
  backendRequest,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const UUID_PATTERN = /^[0-9a-f-]{36}$/i;

export async function POST(
  _request: Request,
  context: { params: Promise<{ document_id: string }> },
) {
  const { document_id } = await context.params;
  if (!UUID_PATTERN.test(document_id)) {
    return Response.json({ detail: "invalid_document_id" }, { status: 422 });
  }
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    return await jsonResponse(
      await backendRequest(`/api/v1/documents/${document_id}/retry`, {
        method: "POST",
        headers: token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {},
      }),
    );
  } catch {
    return unavailableResponse();
  }
}
