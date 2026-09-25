"""Fixed read-only paper tools exposed to the model."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.agent.contracts import (
    AgentSearchContext,
    AuthorWorksArgs,
    ComparePapersArgs,
    GetArxivArgs,
    GetAuthorArgs,
    GetPaperArgs,
    OpenAlexAuthorSearchArgs,
    OpenAlexCitationArgs,
    OpenAlexSearchArgs,
    RelatedPapersArgs,
    RetrieveEvidenceArgs,
    SearchArxivArgs,
    SearchPapersArgs,
)
from app.embeddings.client import EmbeddingError, EmbeddingProvider
from app.retrieval.bm25 import BM25Index
from app.sources.arxiv import ArxivClient, ArxivError
from app.sources.openalex import OpenAlexClient, OpenAlexError
from app.storage.repository import PaperStore, StoreError

MAX_CORPUS_SCAN = 50
MAX_ABSTRACT_CHARS = 3_000
MAX_SEARCH_CONTEXT_ITEMS = 30
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_papers",
        "description": "Search the local imported OpenAlex metadata catalog with BM25.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "from_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "to_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "open_access_only": {"type": ["boolean", "null"]},
            },
            "required": ["query", "limit", "from_year", "to_year", "open_access_only"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_paper_details",
        "description": "Read one exact paper by its OpenAlex Work ID.",
        "parameters": {
            "type": "object",
            "properties": {"openalex_id": {"type": "string", "pattern": "^W[0-9]+$"}},
            "required": ["openalex_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "find_related_papers",
        "description": "Find lexical neighbors in the local catalog; this is not a citation graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_id": {"type": "string", "pattern": "^W[0-9]+$"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["openalex_id", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "expand_openalex_citations",
        "description": (
            "Discover a bounded citation neighborhood for one OpenAlex seed: its references, "
            "works that cite it, or both. Citation edges show metadata links only, not agreement."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_id": {"type": "string", "pattern": "^W[0-9]+$"},
                "direction": {"type": "string", "enum": ["references", "cited_by", "both"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "from_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "to_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "open_access_only": {"type": ["boolean", "null"]},
            },
            "required": [
                "openalex_id",
                "direction",
                "limit",
                "from_year",
                "to_year",
                "open_access_only",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "compare_papers",
        "description": "Compare metadata fields for 2-5 exact OpenAlex Work IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_ids": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^W[0-9]+$"},
                    "minItems": 2,
                    "maxItems": 5,
                }
            },
            "required": ["openalex_ids"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "retrieve_paper_evidence",
        "description": (
            "Search approved CC0/CC BY chunks by BM25, Dense or Hybrid. Dense/Hybrid require an "
            "enabled embedding provider and a current vector index; returns cited excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                "source_type": {"type": ["string", "null"], "enum": ["openalex", "arxiv", None]},
                "source_id": {"type": ["string", "null"], "minLength": 4, "maxLength": 64},
                "retrieval_method": {"type": "string", "enum": ["bm25", "dense", "hybrid"]},
            },
            "required": ["query", "limit", "source_type", "source_id", "retrieval_method"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class PaperToolRegistry:
    def __init__(
        self,
        store: PaperStore,
        openalex: OpenAlexClient | None = None,
        arxiv: ArxivClient | None = None,
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self.store = store
        self.openalex = openalex
        self.arxiv = arxiv
        self.embeddings = embeddings
        self._handlers: dict[str, tuple[type, Callable[[Any], dict[str, Any]]]] = {
            "search_papers": (SearchPapersArgs, self._search),
            "get_paper_details": (GetPaperArgs, self._details),
            "find_related_papers": (RelatedPapersArgs, self._related),
            "compare_papers": (ComparePapersArgs, self._compare),
            "retrieve_paper_evidence": (RetrieveEvidenceArgs, self._retrieve_evidence),
        }
        if openalex is not None:
            self._handlers.update(
                {
                    "expand_openalex_citations": (
                        OpenAlexCitationArgs,
                        self._expand_openalex_citations,
                    ),
                    "search_openalex_works": (OpenAlexSearchArgs, self._search_openalex_works),
                    "get_openalex_work": (GetPaperArgs, self._get_openalex_work),
                    "search_openalex_authors": (
                        OpenAlexAuthorSearchArgs,
                        self._search_openalex_authors,
                    ),
                    "get_openalex_author": (GetAuthorArgs, self._get_openalex_author),
                    "list_openalex_author_works": (
                        AuthorWorksArgs,
                        self._list_openalex_author_works,
                    ),
                }
            )
        if arxiv is not None:
            self._handlers.update(
                {
                    "search_arxiv_metadata": (SearchArxivArgs, self._search_arxiv),
                    "get_arxiv_metadata": (GetArxivArgs, self._get_arxiv),
                }
            )

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [
            json.loads(json.dumps(item))
            for item in TOOL_DEFINITIONS
            if item["name"] in self._handlers
        ]

    def execute(self, name: str, arguments: str) -> dict[str, Any]:
        entry = self._handlers.get(name)
        if entry is None:
            return {"status": "error", "code": "tool_not_allowed"}
        argument_model, handler = entry
        try:
            parsed = argument_model.model_validate_json(arguments)
        except (ValidationError, ValueError):
            return {"status": "error", "code": "invalid_arguments"}
        try:
            return handler(parsed)
        except (sqlite3.Error, StoreError):
            return {"status": "error", "code": "catalog_unavailable"}
        except OpenAlexError as error:
            return {"status": "error", "code": error.code}
        except ArxivError as error:
            return {"status": "error", "code": error.code}
        except Exception:
            return {"status": "error", "code": "tool_failed"}

    def load_search_context(self, context: AgentSearchContext) -> dict[str, Any]:
        """Re-fetch the visible search scope from trusted sources for the Agent."""
        try:
            if context.source == "openalex":
                if self.openalex is None:
                    return {"status": "error", "code": "openalex_unavailable"}
                items = []
                total = 0
                for page_number in range(1, context.pages + 1):
                    page = self.openalex.search_works(
                        context.query,
                        page=page_number,
                        per_page=10,
                        from_year=context.from_year,
                        to_year=context.to_year,
                    )
                    total = page.meta.count
                    items.extend(_openalex_work_observation(work) for work in page.results)
                    if not page.results:
                        break
                return {
                    "status": "ok" if items else "no_results",
                    "source": "openalex",
                    "query": context.query,
                    "from_year": context.from_year,
                    "to_year": context.to_year,
                    "visible_page_count": context.pages,
                    "total_matching_count": total,
                    "items": [self._compact_context_item(item) for item in items],
                }
            if context.source == "arxiv":
                if self.arxiv is None:
                    return {"status": "error", "code": "arxiv_unavailable"}
                items = []
                total = 0
                for page_number in range(context.pages):
                    page = self.arxiv.search(
                        context.query,
                        start=page_number * 10,
                        max_results=10,
                        from_year=context.from_year,
                        to_year=context.to_year,
                    )
                    total = page.total_results
                    items.extend(_arxiv_work_observation(work) for work in page.works)
                    if not page.works:
                        break
                return {
                    "status": "ok" if items else "no_results",
                    "source": "arxiv",
                    "query": context.query,
                    "from_year": context.from_year,
                    "to_year": context.to_year,
                    "visible_page_count": context.pages,
                    "total_matching_count": total,
                    "items": [self._compact_context_item(item) for item in items],
                }

            openalex_result = self.store.list_papers(
                query=context.query or None,
                limit=context.pages * 10,
                offset=0,
            )
            arxiv_result = self.store.list_arxiv_papers(
                query=context.query or None,
                limit=context.pages * 10,
                offset=0,
            )
            items = []
            for paper in openalex_result["items"]:
                year = paper.get("publication_year")
                if context.from_year is not None and (year is None or year < context.from_year):
                    continue
                if context.to_year is not None and (year is None or year > context.to_year):
                    continue
                items.append(self._compact_context_item(_paper_observation(paper)))
            for paper in arxiv_result["items"]:
                try:
                    year = int(paper["published_at"][:4])
                except (KeyError, TypeError, ValueError):
                    year = None
                if context.from_year is not None and (year is None or year < context.from_year):
                    continue
                if context.to_year is not None and (year is None or year > context.to_year):
                    continue
                items.append(
                    self._compact_context_item(
                        {
                            "arxiv_id": paper["arxiv_id"],
                            "title": paper["title"],
                            "publication_year": year,
                            "doi": paper.get("doi"),
                            "source_url": paper["source_url"],
                        }
                    )
                )
            # The local UI pages each source independently, so three loaded
            # pages can contain up to 60 rows. Keep the Agent context within
            # the documented 30-item budget and mirror the UI's year-descending
            # merged order (stable ties retain OpenAlex before arXiv).
            items.sort(
                key=lambda item: item.get("publication_year") or 0,
                reverse=True,
            )
            return {
                "status": "ok" if items else "no_results",
                "source": "library",
                "query": context.query,
                "from_year": context.from_year,
                "to_year": context.to_year,
                "total_matching_count": openalex_result["total"] + arxiv_result["total"],
                "items": items[: min(context.pages * 20, MAX_SEARCH_CONTEXT_ITEMS)],
            }
        except (sqlite3.Error, StoreError):
            return {"status": "error", "code": "catalog_unavailable"}
        except OpenAlexError as error:
            return {"status": "error", "code": error.code}
        except ArxivError as error:
            return {"status": "error", "code": error.code}
        except Exception:
            return {"status": "error", "code": "tool_failed"}

    @staticmethod
    def _compact_context_item(item: dict[str, Any]) -> dict[str, Any]:
        """Keep only bibliography fields needed for answer grounding and citations."""
        keys = {
            "openalex_id",
            "arxiv_id",
            "title",
            "publication_year",
            "published_at",
            "doi",
            "source_url",
            "cited_by_count",
        }
        return {key: value for key, value in item.items() if key in keys}

    def _list_catalog(self) -> tuple[list[dict[str, Any]], int]:
        catalog = self.store.list_papers(query=None, limit=MAX_CORPUS_SCAN, offset=0)
        return catalog["items"], catalog["total"]

    def _search(self, args: SearchPapersArgs) -> dict[str, Any]:
        papers, total = self._list_catalog()
        index = BM25Index(papers)
        hits = index.search(args.query, limit=args.limit)
        by_id = {paper["openalex_id"]: paper for paper in papers}
        return {
            "status": "ok" if hits else "no_results",
            "scanned_documents": len(papers),
            "catalog_documents": total,
            "truncated": total > len(papers),
            "items": [
                {"score": round(hit.score, 6), **_paper_observation(by_id[hit.openalex_id])}
                for hit in hits
            ],
        }

    def _details(self, args: GetPaperArgs) -> dict[str, Any]:
        paper = self.store.get_paper(args.openalex_id)
        if paper is None:
            return {"status": "not_found", "openalex_id": args.openalex_id}
        return {"status": "ok", "paper": _paper_observation(paper)}

    def _related(self, args: RelatedPapersArgs) -> dict[str, Any]:
        source = self.store.get_paper(args.openalex_id)
        if source is None:
            return {"status": "not_found", "openalex_id": args.openalex_id}
        papers, total = self._list_catalog()
        candidates = [paper for paper in papers if paper["openalex_id"] != args.openalex_id]
        source_text = f"{source['title'] or ''} {source['abstract'] or ''}".strip()
        hits = BM25Index(candidates).search(source_text, limit=args.limit)
        by_id = {paper["openalex_id"]: paper for paper in candidates}
        return {
            "status": "ok" if hits else "no_results",
            "method": "bm25_lexical_similarity",
            "catalog_documents": total,
            "truncated": total > len(papers),
            "items": [
                {"score": round(hit.score, 6), **_paper_observation(by_id[hit.openalex_id])}
                for hit in hits
            ],
        }

    def _compare(self, args: ComparePapersArgs) -> dict[str, Any]:
        papers = [self.store.get_paper(openalex_id) for openalex_id in args.openalex_ids]
        missing = [
            openalex_id
            for openalex_id, paper in zip(args.openalex_ids, papers, strict=True)
            if paper is None
        ]
        if missing:
            return {"status": "not_found", "missing_openalex_ids": missing}
        return {
            "status": "ok",
            "comparison_basis": "source metadata only; no claims about methods or findings",
            "papers": [
                {
                    "openalex_id": paper["openalex_id"],
                    "title": paper["title"],
                    "publication_year": paper["publication_year"],
                    "work_type": paper["type"],
                    "cited_by_count": paper["cited_by_count"],
                    "abstract_status": paper["abstract_status"],
                    "source_url": paper["source_url"],
                }
                for paper in papers
                if paper is not None
            ],
        }

    def _retrieve_evidence(self, args: RetrieveEvidenceArgs) -> dict[str, Any]:
        query_embedding = None
        embedding_model = None
        embedding_input_tokens = 0
        if args.retrieval_method != "bm25":
            if self.embeddings is None:
                return {"status": "embedding_unavailable"}
            try:
                batch = self.embeddings.embed([args.query])
            except EmbeddingError as error:
                return {"status": "embedding_error", "code": error.code}
            query_embedding = batch.vectors[0]
            embedding_model = batch.model
            embedding_input_tokens = batch.input_tokens
        result = self.store.search_fulltext_evidence(
            args.query,
            limit=args.limit,
            source_type=args.source_type,
            source_id=args.source_id,
            retrieval_method=args.retrieval_method,
            query_embedding=query_embedding,
            embedding_model=embedding_model,
        )
        if args.retrieval_method != "bm25":
            result["_embedding_input_tokens"] = embedding_input_tokens
        return result

    def _search_openalex_works(self, args: OpenAlexSearchArgs) -> dict[str, Any]:
        assert self.openalex is not None
        page = self.openalex.search_works(
            args.query,
            per_page=args.limit,
            from_year=args.from_year,
            to_year=args.to_year,
            open_access_only=args.open_access_only is True,
        )
        items = [_openalex_work_observation(work) for work in page.results]
        return {
            "status": "ok" if items else "no_results",
            "items": items,
            "total_matching_count": page.meta.count,
            "source": "openalex",
        }

    def _get_openalex_work(self, args: GetPaperArgs) -> dict[str, Any]:
        assert self.openalex is not None
        work = self.openalex.get_work(args.openalex_id)
        return {"status": "ok", "paper": _openalex_work_observation(work)}

    def _expand_openalex_citations(self, args: OpenAlexCitationArgs) -> dict[str, Any]:
        assert self.openalex is not None
        seed = self.openalex.get_work(args.openalex_id)
        candidates: dict[str, dict[str, Any]] = {}

        if args.direction in {"references", "both"}:
            reference_ids = [
                value.rsplit("/", maxsplit=1)[-1] for value in seed.referenced_works[: args.limit]
            ]
            if reference_ids:
                page = self.openalex.get_referenced_works(
                    reference_ids,
                    per_page=args.limit,
                    from_year=args.from_year,
                    to_year=args.to_year,
                    open_access_only=args.open_access_only is True,
                )
                for work in page.results:
                    item = _citation_candidate_observation(work)
                    candidates[item["openalex_id"]] = {
                        **item,
                        "citation_relationships": [
                            {"direction": "references", "seed_openalex_id": args.openalex_id}
                        ],
                    }

        if args.direction in {"cited_by", "both"}:
            page = self.openalex.get_citing_works(
                args.openalex_id,
                per_page=args.limit,
                from_year=args.from_year,
                to_year=args.to_year,
                open_access_only=args.open_access_only is True,
            )
            for work in page.results:
                work_id = work.id.rsplit("/", maxsplit=1)[-1]
                item = candidates.get(work_id) or _citation_candidate_observation(work)
                relations = list(item.get("citation_relationships", []))
                relations.append({"direction": "cited_by", "seed_openalex_id": args.openalex_id})
                candidates[work_id] = {**item, "citation_relationships": relations}

        items = list(candidates.values())[: args.limit * (2 if args.direction == "both" else 1)]
        return {
            "status": "ok" if items else "no_results",
            "source": "openalex",
            "seed_openalex_id": args.openalex_id,
            "direction": args.direction,
            "items": items,
            "metadata_only_relationships": True,
        }

    def _search_openalex_authors(self, args: OpenAlexAuthorSearchArgs) -> dict[str, Any]:
        assert self.openalex is not None
        page = self.openalex.search_authors(args.query, per_page=args.limit)
        return {
            "status": "ok" if page.results else "no_results",
            "items": page.results,
            "total_matching_count": page.meta.count,
            "source": "openalex",
        }

    def _get_openalex_author(self, args: GetAuthorArgs) -> dict[str, Any]:
        assert self.openalex is not None
        return {"status": "ok", "author": self.openalex.get_author(args.openalex_author_id)}

    def _list_openalex_author_works(self, args: AuthorWorksArgs) -> dict[str, Any]:
        assert self.openalex is not None
        page = self.openalex.list_author_works(args.openalex_author_id, per_page=args.limit)
        return {
            "status": "ok" if page.results else "no_results",
            "items": [_openalex_work_observation(work) for work in page.results],
            "total_matching_count": page.meta.count,
            "source": "openalex",
        }

    def _search_arxiv(self, args: SearchArxivArgs) -> dict[str, Any]:
        assert self.arxiv is not None
        page = self.arxiv.search(
            args.query,
            max_results=args.limit,
            from_year=args.from_year,
            to_year=args.to_year,
        )
        return {
            "status": "ok" if page.works else "no_results",
            "items": [_arxiv_work_observation(work) for work in page.works],
            "total_matching_count": page.total_results,
            "source": "arxiv",
            "submitted_date_filter": {
                "from_year": args.from_year,
                "to_year": args.to_year,
                "semantics": "arXiv submission date; not a journal publication year or license",
            },
        }

    def _get_arxiv(self, args: GetArxivArgs) -> dict[str, Any]:
        assert self.arxiv is not None
        work = self.arxiv.get_work(args.arxiv_id)
        if work is None:
            return {"status": "not_found", "arxiv_id": args.arxiv_id}
        return {"status": "ok", "paper": _arxiv_work_observation(work)}


def _paper_observation(paper: dict[str, Any]) -> dict[str, Any]:
    abstract = paper.get("abstract")
    return {
        "openalex_id": paper["openalex_id"],
        "title": (paper.get("title") or "")[:500],
        "publication_year": paper.get("publication_year"),
        "abstract": abstract[:MAX_ABSTRACT_CHARS] if isinstance(abstract, str) else None,
        "abstract_truncated": isinstance(abstract, str) and len(abstract) > MAX_ABSTRACT_CHARS,
        "abstract_status": paper.get("abstract_status"),
        "source_url": paper["source_url"],
        "metadata_license": paper.get("metadata_license"),
    }


def _openalex_work_observation(work: Any) -> dict[str, Any]:
    work_id = work.id.rsplit("/", maxsplit=1)[-1]
    from app.storage.repository import _reconstruct_abstract

    abstract, abstract_status = _reconstruct_abstract(work.abstract_inverted_index)
    return {
        "openalex_id": work_id,
        "title": (work.title or work.display_name or "")[:500],
        "publication_year": work.publication_year,
        "abstract": abstract[:MAX_ABSTRACT_CHARS] if abstract else None,
        "abstract_truncated": bool(abstract and len(abstract) > MAX_ABSTRACT_CHARS),
        "abstract_status": abstract_status,
        "source_url": work.id,
        "doi": work.doi,
        "metadata_license": "CC0-1.0",
        "cited_by_count": work.cited_by_count,
        "is_open_access": (
            work.open_access.get("is_oa") if isinstance(work.open_access, dict) else None
        ),
        "referenced_works": work.referenced_works[:50],
    }


def _citation_candidate_observation(work: Any) -> dict[str, Any]:
    item = _openalex_work_observation(work)
    abstract = item.get("abstract")
    if isinstance(abstract, str) and len(abstract) > 1_000:
        item["abstract"] = abstract[:1_000]
        item["abstract_truncated"] = True
    item.pop("referenced_works", None)
    return item


def _arxiv_work_observation(work: Any) -> dict[str, Any]:
    return {
        "arxiv_id": work.arxiv_id,
        "title": work.title[:500],
        "abstract": work.abstract[:MAX_ABSTRACT_CHARS],
        "abstract_truncated": len(work.abstract) > MAX_ABSTRACT_CHARS,
        "authors": work.authors[:50],
        "categories": work.categories[:30],
        "primary_category": work.primary_category,
        "published_at": work.published_at.isoformat(),
        "updated_at": work.updated_at.isoformat(),
        "doi": work.doi,
        "source_url": f"https://arxiv.org/abs/{work.arxiv_id}",
        "metadata_license": "CC0-1.0",
    }


def _search_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _openalex_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "search_openalex_works",
        "description": "Search OpenAlex Works metadata with optional year and open-access filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "from_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "to_year": {"type": ["integer", "null"], "minimum": 1400, "maximum": 2100},
                "open_access_only": {"type": ["boolean", "null"]},
            },
            "required": ["query", "limit", "from_year", "to_year", "open_access_only"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _arxiv_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "search_arxiv_metadata",
        "description": (
            "Search arXiv metadata only. Optional year filters apply to arXiv submission date; "
            "arXiv search does not certify OpenAlex OA status or reuse license."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "from_year": {"type": ["integer", "null"], "minimum": 1991, "maximum": 2100},
                "to_year": {"type": ["integer", "null"], "minimum": 1991, "maximum": 2100},
            },
            "required": ["query", "limit", "from_year", "to_year"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _get_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {"openalex_id": {"type": "string", "pattern": "^W[0-9]+$"}},
            "required": ["openalex_id"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _get_author_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "get_openalex_author",
        "description": "Read one live OpenAlex Author by ID.",
        "parameters": {
            "type": "object",
            "properties": {"openalex_author_id": {"type": "string", "pattern": "^A[0-9]+$"}},
            "required": ["openalex_author_id"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _author_works_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "list_openalex_author_works",
        "description": "List a bounded page of works associated with one OpenAlex Author ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_author_id": {"type": "string", "pattern": "^A[0-9]+$"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["openalex_author_id", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    }


TOOL_DEFINITIONS.extend(
    [
        _openalex_search_tool(),
        _get_tool("get_openalex_work", "Read one live OpenAlex Work by ID."),
        _search_tool("search_openalex_authors", "Search live OpenAlex author metadata."),
        _get_author_tool(),
        _author_works_tool(),
    ]
)

TOOL_DEFINITIONS.extend(
    [
        _arxiv_search_tool(),
        {
            "type": "function",
            "name": "get_arxiv_metadata",
            "description": "Read one arXiv metadata record by ID; never fetch paper files.",
            "parameters": {
                "type": "object",
                "properties": {"arxiv_id": {"type": "string", "minLength": 4, "maxLength": 64}},
                "required": ["arxiv_id"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]
)
