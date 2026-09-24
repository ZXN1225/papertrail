import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const query = (params.get("q") ?? "").trim();
  const sourceType = params.get("source_type");
  const sourceId = params.get("source_id");
  const method = params.get("retrieval_method") ?? "bm25";
  if (!query || query.length > 256)
    return invalidResponse("请输入 1–256 个字符的问题。");
  if (!new Set(["bm25", "dense", "hybrid"]).has(method)) {
    return invalidResponse("检索方式无效。");
  }
  if (
    (sourceType === null) !== (sourceId === null) ||
    (sourceType !== null && !["openalex", "arxiv"].includes(sourceType)) ||
    (sourceId !== null && sourceId.length > 64)
  ) {
    return invalidResponse("论文来源筛选无效。");
  }
  const queryString = new URLSearchParams({
    q: query,
    limit: "5",
    retrieval_method: method,
  });
  if (sourceType && sourceId) {
    queryString.set("source_type", sourceType);
    queryString.set("source_id", sourceId);
  }
  try {
    return await jsonResponse(
      await backendRequest(`/api/v1/evidence/search?${queryString.toString()}`),
    );
  } catch {
    return unavailableResponse();
  }
}
