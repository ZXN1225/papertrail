import { NextRequest } from "next/server";
import { cookies } from "next/headers";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ run_id: string }> },
) {
  const { run_id: runId } = await context.params;
  if (!UUID_PATTERN.test(runId)) return invalidResponse("任务标识无效。");
  try {
    const session = (await cookies()).get("papertrail_session")?.value;
    return await jsonResponse(
      await backendRequest(`/api/v1/agent/runs/${encodeURIComponent(runId)}`, {
        headers: session
          ? { Cookie: `papertrail_session=${encodeURIComponent(session)}` }
          : {},
      }),
    );
  } catch {
    return unavailableResponse();
  }
}
