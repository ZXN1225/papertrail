import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";
import {
  normalizeArxiv,
  normalizeLocalOpenAlex,
  normalizeOpenAlex,
  type Paper,
  type Source,
} from "@/lib/api/papers";

const SOURCES = new Set<Source>(["openalex", "arxiv", "library"]);

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const source = params.get("source") as Source | null;
  const query = (params.get("q") ?? "").trim();
  if (!source || !SOURCES.has(source))
    return invalidResponse("请选择有效的数据来源。");
  if (query.length > 256) return invalidResponse("检索词最多 256 个字符。");
  if (source !== "library" && !query)
    return invalidResponse("请输入论文检索词。");

  try {
    if (source === "openalex") {
      const upstream = await backendRequest(
        `/api/v1/papers/search?q=${encodeURIComponent(query)}&per_page=10`,
      );
      const result = await upstream.json();
      if (!upstream.ok)
        return Response.json(result, { status: upstream.status });
      const items = Array.isArray(result.results)
        ? result.results
            .map(normalizeOpenAlex)
            .filter((paper: Paper) => paper.id)
        : [];
      return Response.json(
        { source, total: result.meta?.count ?? items.length, items },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    if (source === "arxiv") {
      const upstream = await backendRequest(
        `/api/v1/arxiv/search?q=${encodeURIComponent(query)}&max_results=10`,
      );
      const result = await upstream.json();
      if (!upstream.ok)
        return Response.json(result, { status: upstream.status });
      const items = Array.isArray(result.works)
        ? result.works.map(normalizeArxiv)
        : [];
      return Response.json(
        { source, total: result.total_results ?? items.length, items },
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    const encodedQuery = query
      ? `?q=${encodeURIComponent(query)}&limit=20`
      : "?limit=20";
    const [openalexResponse, arxivResponse] = await Promise.all([
      backendRequest(`/api/v1/catalog/papers${encodedQuery}`),
      backendRequest(`/api/v1/catalog/arxiv${encodedQuery}`),
    ]);
    const [openalex, arxiv] = await Promise.all([
      openalexResponse.json(),
      arxivResponse.json(),
    ]);
    if (!openalexResponse.ok || !arxivResponse.ok) {
      return Response.json(
        {
          detail: {
            code: "catalog_unavailable",
            message: "本地论文目录暂时不可用。",
          },
        },
        { status: 503 },
      );
    }
    const items = [
      ...(Array.isArray(openalex.items)
        ? openalex.items.map(normalizeLocalOpenAlex)
        : []),
      ...(Array.isArray(arxiv.items) ? arxiv.items.map(normalizeArxiv) : []),
    ].sort((left, right) => (right.year ?? 0) - (left.year ?? 0));
    return Response.json(
      { source, total: (openalex.total ?? 0) + (arxiv.total ?? 0), items },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return unavailableResponse();
  }
}
