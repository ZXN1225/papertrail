"""Application service wiring the configured model to the bounded agent harness."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.agent.contracts import AgentResponse, AgentTraceEvent, AgentTurn
from app.agent.model import ModelClient, OpenAIResponsesClient
from app.agent.research_runtime import ResearchRuntime
from app.agent.tools import PaperToolRegistry
from app.config import Settings
from app.embeddings.client import OpenAIEmbeddingClient
from app.sources.arxiv import ArxivClient
from app.sources.openalex import OpenAlexClient
from app.storage.repository import PaperStore


class AgentService:
    def __init__(
        self,
        settings: Settings,
        store: PaperStore,
        *,
        model: ModelClient | None = None,
        openalex: OpenAlexClient | None = None,
        arxiv: ArxivClient | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.model = model
        self.openalex = openalex
        self.arxiv = arxiv

    def ask(
        self,
        question: str,
        *,
        history: Sequence[AgentTurn] = (),
        prior_user_questions: Sequence[str] | None = None,
        memory: dict | None = None,
        user_library: Sequence[tuple[str, str]] = (),
        user_id: str | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int, Sequence[AgentTraceEvent]], None] | None = None,
    ) -> AgentResponse:
        documents = []
        if user_id:
            with self.store._connection() as db:
                rows = db.execute(
                    "SELECT DISTINCT source_type,source_id,title FROM user_documents "
                    "WHERE user_id=? AND state='indexed' ORDER BY title",
                    (user_id,),
                ).fetchall()
            documents = [dict(row) for row in rows]
        if self.model is None and self.settings.llm_provider == "disabled":
            return AgentResponse(
                status="model_disabled",
                answer="语言模型尚未启用。请在服务端配置 LLM_PROVIDER、LLM_API_KEY 和 LLM_MODEL。",
            )
        client = self.model or OpenAIResponsesClient(self.settings)
        embeddings = (
            OpenAIEmbeddingClient(self.settings)
            if self.settings.embedding_provider == "openai"
            else None
        )
        openalex = self.openalex or OpenAlexClient(
            api_key=(
                self.settings.openalex_api_key.get_secret_value()
                if self.settings.openalex_api_key
                else None
            ),
            # Agent requests must tolerate ordinary OpenAlex latency. The
            # previous 4-second, no-retry setting caused otherwise healthy
            # searches to fail while the discovery endpoint still worked.
            timeout_seconds=12,
            max_retries=1,
        )
        arxiv = self.arxiv or ArxivClient(timeout_seconds=4)
        try:
            registry = PaperToolRegistry(self.store, openalex, arxiv, embeddings, user_id=user_id)
            return ResearchRuntime(
                self.settings,
                client,
                registry,
                cancelled=cancellation_requested,
                progress=progress_callback,
            ).run(
                question,
                history,
                documents,
                memory or {},
            )
        finally:
            if self.model is None:
                client.close()
            if embeddings is not None:
                embeddings.close()
            if self.openalex is None:
                openalex.close()
            if self.arxiv is None:
                arxiv.close()
