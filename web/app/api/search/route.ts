import { NextRequest } from "next/server";
import { cookies } from "next/headers";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/api/backend";
import {
  normalizeArxiv,
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

    const cookieJar = await cookies();
    const token = cookieJar.get("papertrail_session")?.value;
    const response = await backendRequest(
      `/api/v1/library?limit=50${query ? `&query=${encodeURIComponent(query)}` : ""}`,
      {
        headers: token
          ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
          : {},
      },
    );
    const entries = await response.json();
    if (!response.ok)
      return Response.json(entries, { status: response.status });
    const items = Array.isArray(entries)
      ? entries.flatMap(
          (entry: { source?: string; metadata?: Record<string, unknown> }) => {
            if (!entry.metadata) return [];
            if (entry.source === "arxiv")
              return [normalizeArxiv(entry.metadata)];
            if (entry.source === "openalex")
              return [normalizeOpenAlex(entry.metadata)];
            return [];
          },
        )
      : [];
    return Response.json(
      { source, total: items.length, items },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return unavailableResponse();
  }
}
