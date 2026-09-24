export type Source = "openalex" | "arxiv" | "library";

export type Paper = {
  id: string;
  source: "openalex" | "arxiv";
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  sourceUrl: string;
  doi: string | null;
  venue: string | null;
  citationCount: number | null;
  categories: string[];
  synthetic?: boolean;
};

export type SearchResponse = {
  source: Source;
  total: number;
  items: Paper[];
};

export type Evidence = {
  chunk_id: string;
  locator: string;
  excerpt: string;
};

export type Citation = {
  source: "openalex" | "arxiv";
  openalex_id: string | null;
  arxiv_id: string | null;
  title: string;
  source_url: string;
  license_id: string | null;
  license_url: string | null;
  attribution: string | null;
  evidence: Evidence[];
};

export type AgentResponse = {
  status: string;
  answer: string;
  citations: Citation[];
  warnings: string[];
  tool_calls: number;
  model_steps: number;
  model_input_tokens: number;
  model_output_tokens: number;
  run_id: string | null;
  duration_ms: number;
  trace: {
    sequence: number;
    kind: "model" | "tool";
    name: string;
    status: string;
    duration_ms: number;
    input_tokens: number;
    output_tokens: number;
  }[];
};

export function normalizeOpenAlex(value: Record<string, unknown>): Paper {
  const rawId = typeof value.id === "string" ? value.id : "";
  const id = rawId.match(/W\d+$/)?.[0] ?? "";
  const authorships = Array.isArray(value.authorships) ? value.authorships : [];
  const authors = authorships.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const author = (entry as { author?: { display_name?: unknown } }).author;
    return typeof author?.display_name === "string"
      ? [author.display_name]
      : [];
  });
  const primary = value.primary_location as
    { source?: { display_name?: unknown } | null } | null | undefined;
  return {
    id,
    source: "openalex",
    title: stringOrNull(value.title ?? value.display_name) ?? "未提供标题",
    authors,
    year: numberOrNull(value.publication_year),
    abstract: reconstructAbstract(value.abstract_inverted_index),
    sourceUrl: id ? `https://openalex.org/${id}` : "https://openalex.org/",
    doi: stringOrNull(value.doi),
    venue: stringOrNull(primary?.source?.display_name),
    citationCount: numberOrNull(value.cited_by_count),
    categories: [],
  };
}

export function normalizeLocalOpenAlex(value: Record<string, unknown>): Paper {
  const id = stringOrNull(value.openalex_id) ?? "";
  return {
    id,
    source: "openalex",
    title: stringOrNull(value.title) ?? "未提供标题",
    authors: stringArray(value.authors),
    year: numberOrNull(value.publication_year),
    abstract: stringOrNull(value.abstract),
    sourceUrl: stringOrNull(value.source_url) ?? `https://openalex.org/${id}`,
    doi: stringOrNull(value.doi),
    venue: stringOrNull(value.venue),
    citationCount: numberOrNull(value.cited_by_count),
    categories: [],
  };
}

export function normalizeArxiv(value: Record<string, unknown>): Paper {
  const id = stringOrNull(value.arxiv_id) ?? "";
  const yearString = stringOrNull(value.published_at);
  return {
    id,
    source: "arxiv",
    title: stringOrNull(value.title) ?? "未提供标题",
    authors: stringArray(value.authors),
    year: yearString ? Number(yearString.slice(0, 4)) || null : null,
    abstract: stringOrNull(value.abstract),
    sourceUrl: stringOrNull(value.source_url) ?? `https://arxiv.org/abs/${id}`,
    doi: stringOrNull(value.doi),
    venue:
      stringOrNull(value.journal_ref) ?? stringOrNull(value.primary_category),
    citationCount: null,
    categories: stringArray(value.categories),
  };
}

export function reconstructAbstract(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const positions = new Map<number, string>();
  for (const [token, indexes] of Object.entries(value)) {
    if (!Array.isArray(indexes)) return null;
    for (const index of indexes) {
      if (
        typeof index !== "number" ||
        !Number.isInteger(index) ||
        positions.has(index)
      ) {
        return null;
      }
      positions.set(index, token);
    }
  }
  if (!positions.size || Math.max(...positions.keys()) > 50_000) return null;
  const result = Array.from(
    { length: Math.max(...positions.keys()) + 1 },
    (_, index) => positions.get(index),
  ).join(" ");
  return result.trim() || null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}
