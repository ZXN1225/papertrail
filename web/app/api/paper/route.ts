import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const source = params.get("source");
  const id = (params.get("id") ?? "").trim();
  if (!id || id.length > 64) return invalidResponse("论文标识无效。");

  let path: string;
  if (source === "openalex" && /^W\d+$/.test(id)) {
    path = `/api/v1/openalex/works/${encodeURIComponent(id)}`;
  } else if (source === "arxiv" && /^\d{4}\.\d{4,5}$/.test(id)) {
    path = `/api/v1/arxiv/works/${encodeURIComponent(id)}`;
  } else if (source === "library" && /^W\d+$/.test(id)) {
    path = `/api/v1/catalog/papers/${encodeURIComponent(id)}`;
  } else if (source === "library" && /^\d{4}\.\d{4,5}$/.test(id)) {
    path = `/api/v1/catalog/arxiv/${encodeURIComponent(id)}`;
  } else {
    return invalidResponse("论文来源和标识不匹配。");
  }

  try {
    return await jsonResponse(await backendRequest(path));
  } catch {
    return unavailableResponse();
  }
}
