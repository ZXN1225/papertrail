import {
  backendRequest,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

export async function GET() {
  try {
    return await jsonResponse(await backendRequest("/api/health/ready"));
  } catch {
    return unavailableResponse();
  }
}
