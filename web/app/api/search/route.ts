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
  const pageValue = params.get("page") ?? "1";
  const page = Number(pageValue);
  const fromYearValue = params.get("from_year");
  const toYearValue = params.get("to_year");
  const fromYear = fromYearValue ? Number(fromYearValue) : null;
  const toYear = toYearValue ? Number(toYearValue) : null;
  if (!source || !SOURCES.has(source))
    return invalidResponse("请选择有效的数据来源。");
  if (query.length > 256) return invalidResponse("检索词最多 256 个字符。");
  if (source !== "library" && !query)
    return invalidResponse("请输入论文检索词。");
  if (!Number.isInteger(page) || page < 1 || page > 1_000)
    return invalidResponse("检索页码必须在 1 到 1000 之间。");
  if (
    (fromYear !== null &&
      (!Number.isInteger(fromYear) || fromYear < 1400 || fromYear > 2100)) ||
    (toYear !== null &&
      (!Number.isInteger(toYear) || toYear < 1400 || toYear > 2100)) ||
    (fromYear !== null && toYear !== null && fromYear > toYear)
  )
    return invalidResponse("发表年份范围无效，请检查起止年份。");

  const yearParams = new URLSearchParams();
  if (fromYear !== null) yearParams.set("from_year", String(fromYear));
  if (toYear !== null) yearParams.set("to_year", String(toYear));
  const yearQuery = yearParams.size ? `&${yearParams.toString()}` : "";

  try {
    if (source === "openalex") {
      const upstream = await backendRequest(
        `/api/v1/papers/search?q=${encodeURIComponent(query)}&page=${page}&per_page=10${yearQuery}`,
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
        {
          source,
          total: result.meta?.count ?? items.length,
          items,
          page,
          hasMore:
            page < 1_000 && page * 10 < (result.meta?.count ?? items.length),
          pageLimitReached:
            page === 1_000 && (result.meta?.count ?? items.length) > 10_000,
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    if (source === "arxiv") {
      const upstream = await backendRequest(
        `/api/v1/arxiv/search?q=${encodeURIComponent(query)}&start=${(page - 1) * 10}&max_results=10${yearQuery}`,
      );
      const result = await upstream.json();
      if (!upstream.ok)
        return Response.json(result, { status: upstream.status });
      const items = Array.isArray(result.works)
        ? result.works.map(normalizeArxiv)
        : [];
      return Response.json(
        {
          source,
          total: result.total_results ?? items.length,
          items,
          page,
          hasMore:
            page < 1_000 && page * 10 < (result.total_results ?? items.length),
          pageLimitReached:
            page === 1_000 && (result.total_results ?? items.length) > 10_000,
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    const offset = (page - 1) * 10;
    const encodedQuery = query
      ? `?q=${encodeURIComponent(query)}&limit=10&offset=${offset}`
      : `?limit=10&offset=${offset}`;
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
    const openAlexItems = Array.isArray(openalex.items)
      ? openalex.items.length
      : 0;
    const arxivItems = Array.isArray(arxiv.items) ? arxiv.items.length : 0;
    const openAlexTotal = openalex.total ?? 0;
    const arxivTotal = arxiv.total ?? 0;
    const total = openAlexTotal + arxivTotal;
    return Response.json(
      {
        source,
        total,
        items,
        page,
        hasMore:
          page < 1_000 &&
          (offset + openAlexItems < openAlexTotal ||
            offset + arxivItems < arxivTotal),
        pageLimitReached: page === 1_000 && total > 10_000,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return unavailableResponse();
  }
}
