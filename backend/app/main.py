"""HTTP entry point for the PaperTrail API."""

import sqlite3

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi import Path as PathParameter

from app.agent.contracts import AgentQuestion, AgentResponse
from app.agent.service import AgentService
from app.config import Settings, get_settings
from app.embeddings.client import EmbeddingError, OpenAIEmbeddingClient
from app.sources.arxiv import ArxivClient, ArxivError
from app.sources.openalex import OpenAlexClient, OpenAlexError
from app.storage.repository import PaperStore, StoreError


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title="PaperTrail API",
        version="0.1.0",
        description="Academic paper discovery and research assistant API.",
    )

    @application.get("/api/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @application.post(
        "/api/v1/agent/ask",
        response_model=AgentResponse,
        tags=["agent"],
    )
    def ask_agent(body: AgentQuestion, response: Response) -> AgentResponse:
        result = AgentService(
            app_settings,
            PaperStore(app_settings.resolved_data_storage_path),
        ).ask(body.question)
        if result.status in {"model_disabled", "model_unavailable"}:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return result

    @application.get("/api/health/ready", tags=["health"])
    def ready(response: Response) -> dict[str, object]:
        try:
            PaperStore(app_settings.resolved_data_storage_path).migrate()
        except (sqlite3.Error, StoreError):
            response.status_code = 503
            return {
                "status": "not_ready",
                "checks": {
                    "application": "available",
                    "database": "unavailable",
                    "openalex": "not_connected",
                    "llm": "disabled" if app_settings.llm_provider == "disabled" else "configured",
                    "embedding": (
                        "disabled"
                        if app_settings.embedding_provider == "disabled"
                        else "configured"
                    ),
                },
            }
        return {
            "status": "ready",
            "checks": {
                "application": "available",
                "database": "sqlite_available",
                "openalex": "not_connected",
                "llm": "disabled" if app_settings.llm_provider == "disabled" else "configured",
                "embedding": (
                    "disabled" if app_settings.embedding_provider == "disabled" else "configured"
                ),
            },
        }

    @application.get("/api/v1/papers/search", tags=["papers"])
    def search_papers(
        q: str = Query(min_length=1, max_length=256),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, object]:
        if not q.strip():
            raise HTTPException(status_code=422, detail="q must contain non-whitespace characters")
        api_key = app_settings.openalex_api_key
        secret = api_key.get_secret_value() if api_key else None
        try:
            with OpenAlexClient(api_key=secret) as client:
                result = client.search_works(q, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/openalex/works/{work_id}", tags=["openalex"])
    def get_openalex_work(work_id: str = PathParameter(pattern=r"^W\d+$")) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                work = client.get_work(work_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return work.model_dump(mode="json")

    @application.get("/api/v1/openalex/authors/search", tags=["openalex"])
    def search_openalex_authors(
        q: str = Query(min_length=1, max_length=256),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                result = client.search_authors(q, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/openalex/authors/{author_id}", tags=["openalex"])
    def get_openalex_author(author_id: str = PathParameter(pattern=r"^A\d+$")) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                return client.get_author(author_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None

    @application.get("/api/v1/openalex/authors/{author_id}/works", tags=["openalex"])
    def list_openalex_author_works(
        author_id: str = PathParameter(pattern=r"^A\d+$"),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                result = client.list_author_works(author_id, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/arxiv/search", tags=["arxiv"])
    def search_arxiv(
        q: str = Query(min_length=1, max_length=256),
        start: int = Query(default=0, ge=0, le=9_975),
        max_results: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with ArxivClient(timeout_seconds=15) as client:
                result = client.search(q, start=start, max_results=max_results)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except ArxivError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/arxiv/works/{arxiv_id}", tags=["arxiv"])
    def get_arxiv_work(
        arxiv_id: str = PathParameter(min_length=4, max_length=64),
    ) -> dict[str, object]:
        try:
            with ArxivClient(timeout_seconds=15) as client:
                work = client.get_work(arxiv_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except ArxivError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        if work is None:
            raise HTTPException(status_code=404, detail="arXiv work not found")
        return work.model_dump(mode="json")

    @application.get("/api/v1/catalog/arxiv", tags=["catalog"])
    def list_catalog_arxiv(
        q: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=10_000),
    ) -> dict[str, object]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_arxiv_papers(
                query=q, limit=limit, offset=offset
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/arxiv/{arxiv_id}", tags=["catalog"])
    def get_catalog_arxiv(
        arxiv_id: str = PathParameter(min_length=4, max_length=64),
    ) -> dict[str, object]:
        try:
            work = PaperStore(app_settings.resolved_data_storage_path).get_arxiv_paper(arxiv_id)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None
        if work is None:
            raise HTTPException(status_code=404, detail="arXiv paper not found")
        return work

    @application.get("/api/v1/evidence/search", tags=["evidence"])
    def search_licensed_evidence(
        q: str = Query(min_length=1, max_length=256),
        limit: int = Query(default=5, ge=1, le=8),
        source_type: str | None = Query(default=None, pattern=r"^(openalex|arxiv)$"),
        source_id: str | None = Query(default=None, min_length=4, max_length=64),
        retrieval_method: str = Query(default="bm25", pattern=r"^(bm25|dense|hybrid)$"),
    ) -> dict[str, object]:
        try:
            query_embedding = None
            embedding_model = None
            if retrieval_method != "bm25":
                if app_settings.embedding_provider == "disabled":
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "embedding_disabled",
                            "message": "Embedding provider 未启用。",
                        },
                    )
                embeddings = OpenAIEmbeddingClient(app_settings)
                try:
                    batch = embeddings.embed([q])
                finally:
                    embeddings.close()
                query_embedding = batch.vectors[0]
                embedding_model = batch.model
            result = PaperStore(app_settings.resolved_data_storage_path).search_fulltext_evidence(
                q,
                limit=limit,
                source_type=source_type,
                source_id=source_id,
                retrieval_method=retrieval_method,
                query_embedding=query_embedding,
                embedding_model=embedding_model,
            )
            if retrieval_method != "bm25":
                result["embedding_usage"] = {
                    "model": embedding_model,
                    "input_tokens": batch.input_tokens,
                    "estimated_cost_usd": _embedding_cost_estimate(
                        app_settings.embedding_price_per_million_usd, batch.input_tokens
                    ),
                }
            return result
        except EmbeddingError as error:
            raise HTTPException(
                status_code=502,
                detail={"code": error.code, "message": "Embedding 服务暂不可用。"},
            ) from None
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "evidence_unavailable", "message": "许可全文检索暂不可用。"},
            ) from None

    @application.get("/api/v1/catalog/papers", tags=["catalog"])
    def list_catalog_papers(
        q: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=10_000),
    ) -> dict[str, object]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_papers(
                query=q, limit=limit, offset=offset
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/papers/{openalex_id}", tags=["catalog"])
    def get_catalog_paper(
        openalex_id: str = PathParameter(pattern=r"^W\d+$"),
        snapshot_id: str | None = Query(default=None, max_length=36),
    ) -> dict[str, object]:
        try:
            paper = PaperStore(app_settings.resolved_data_storage_path).get_paper(
                openalex_id, snapshot_id=snapshot_id
            )
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None
        if paper is None:
            raise HTTPException(status_code=404, detail="paper not found in requested snapshot")
        return paper

    @application.get("/api/v1/catalog/snapshots", tags=["catalog"])
    def list_catalog_snapshots(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict[str, object]]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_snapshots(limit=limit)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地快照记录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/snapshots/{snapshot_id}", tags=["catalog"])
    def get_catalog_snapshot(
        snapshot_id: str = PathParameter(min_length=36, max_length=36),
    ) -> dict[str, object]:
        try:
            snapshot = PaperStore(app_settings.resolved_data_storage_path).get_snapshot(snapshot_id)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地快照记录暂时不可用。"},
            ) from None
        if snapshot is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return snapshot

    return application


def _embedding_cost_estimate(
    price_per_million_usd: float | None, input_tokens: int
) -> float | None:
    if price_per_million_usd is None:
        return None
    return round(price_per_million_usd * input_tokens / 1_000_000, 10)


def _openalex_client(settings: Settings) -> OpenAlexClient:
    secret = settings.openalex_api_key.get_secret_value() if settings.openalex_api_key else None
    return OpenAlexClient(api_key=secret)


app = create_app()
