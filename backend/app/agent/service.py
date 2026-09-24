"""Application service wiring the configured model to the bounded agent harness."""

from __future__ import annotations

from app.agent.contracts import AgentResponse
from app.agent.harness import AgentHarness
from app.agent.model import ModelClient, OpenAIResponsesClient
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

    def ask(self, question: str) -> AgentResponse:
        if self.model is not None:
            harness = self._harness(self.model, self.openalex, self.arxiv)
            return harness.run(question)
        if self.settings.llm_provider == "disabled":
            return AgentResponse(
                status="model_disabled",
                answer="语言模型尚未启用。请在服务端配置 LLM_PROVIDER、LLM_API_KEY 和 LLM_MODEL。",
            )
        client = OpenAIResponsesClient(self.settings)
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
            timeout_seconds=4,
            max_retries=0,
        )
        arxiv = self.arxiv or ArxivClient(timeout_seconds=4)
        try:
            return self._harness(client, openalex, arxiv, embeddings).run(question)
        finally:
            client.close()
            if embeddings is not None:
                embeddings.close()
            if self.openalex is None:
                openalex.close()
            if self.arxiv is None:
                arxiv.close()

    def _harness(
        self,
        model: ModelClient,
        openalex: OpenAlexClient | None = None,
        arxiv: ArxivClient | None = None,
        embeddings: OpenAIEmbeddingClient | None = None,
    ) -> AgentHarness:
        return AgentHarness(
            model,
            PaperToolRegistry(self.store, openalex, arxiv, embeddings),
            max_steps=self.settings.agent_max_steps,
            max_tool_calls=self.settings.agent_max_tool_calls,
            deadline_seconds=self.settings.agent_deadline_seconds,
        )
