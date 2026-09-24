"""Fixed read-only paper tools exposed to the model."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.agent.contracts import (
    AuthorWorksArgs,
    ComparePapersArgs,
    GetArxivArgs,
    GetAuthorArgs,
    GetPaperArgs,
    OpenAlexAuthorSearchArgs,
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
            },
            "required": ["query", "limit"],
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
        page = self.openalex.search_works(args.query, per_page=args.limit)
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
        page = self.arxiv.search(args.query, max_results=args.limit)
        return {
            "status": "ok" if page.works else "no_results",
            "items": [_arxiv_work_observation(work) for work in page.works],
            "total_matching_count": page.total_results,
            "source": "arxiv",
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
        "metadata_license": "CC0-1.0",
        "cited_by_count": work.cited_by_count,
        "referenced_works": work.referenced_works[:50],
    }


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
        _search_tool("search_openalex_works", "Search live OpenAlex Works metadata; no full text."),
        _get_tool("get_openalex_work", "Read one live OpenAlex Work by ID."),
        _search_tool("search_openalex_authors", "Search live OpenAlex author metadata."),
        _get_author_tool(),
        _author_works_tool(),
    ]
)

TOOL_DEFINITIONS.extend(
    [
        _search_tool(
            "search_arxiv_metadata", "Search arXiv metadata only; never fetch paper files."
        ),
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
