import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return invalidResponse("任务标识无效。");
  }
  if (
    !body ||
    typeof body !== "object" ||
    Object.keys(body).length !== 1 ||
    typeof (body as { run_id?: unknown }).run_id !== "string" ||
    !UUID_PATTERN.test((body as { run_id: string }).run_id)
  ) {
    return invalidResponse("任务标识无效。");
  }
  try {
    return await jsonResponse(
      await backendRequest(
        `/api/v1/agent/runs/${encodeURIComponent((body as { run_id: string }).run_id)}/cancel`,
        { method: "POST" },
      ),
    );
  } catch {
    return unavailableResponse();
  }
}
