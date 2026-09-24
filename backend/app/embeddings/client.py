"""OpenAI embeddings adapter with a fixed endpoint and validated bounded batches."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

API_URL = "https://api.openai.com/v1/embeddings"
MAX_BATCH_SIZE = 64
MAX_INPUT_CHARS = 8_000


class EmbeddingError(RuntimeError):
    """Safe embedding provider failure; never contains credentials or raw response text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EmbeddingBatch:
    model: str
    vectors: list[list[float]]
    input_tokens: int


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: list[str]) -> EmbeddingBatch: ...


class OpenAIEmbeddingClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if (
            settings.embedding_provider != "openai"
            or settings.embedding_api_key is None
            or not settings.embedding_model
        ):
            raise ValueError("OpenAI embedding provider is not configured")
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.api_key = settings.embedding_api_key.get_secret_value()
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout_seconds), follow_redirects=False
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not 1 <= len(texts) <= MAX_BATCH_SIZE:
            raise EmbeddingError("invalid_batch_size")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError("empty_input")
        if any(len(text) > MAX_INPUT_CHARS for text in texts):
            raise EmbeddingError("input_too_large")
        payload: dict[str, object] = {"model": self.model, "input": texts}
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        try:
            response = self.client.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as error:
            raise EmbeddingError("timeout") from error
        except httpx.HTTPError as error:
            raise EmbeddingError("provider_unavailable") from error
        if response.status_code in {401, 403}:
            raise EmbeddingError("authentication_failed")
        if response.status_code == 429:
            raise EmbeddingError("rate_limited")
        if response.status_code >= 500:
            raise EmbeddingError("provider_unavailable")
        if response.status_code >= 400:
            raise EmbeddingError("request_rejected")
        try:
            body = response.json()
            if body.get("model") != self.model:
                raise ValueError("model mismatch")
            rows = body["data"]
            if len(rows) != len(texts):
                raise ValueError("embedding count mismatch")
            rows = sorted(rows, key=lambda row: row["index"])
            if [row["index"] for row in rows] != list(range(len(texts))):
                raise ValueError("embedding indices must be complete and unique")
            vectors = [row["embedding"] for row in rows]
            dimensions = self.dimensions or (len(vectors[0]) if vectors else 0)
            if dimensions <= 0 or any(len(vector) != dimensions for vector in vectors):
                raise ValueError("embedding dimension mismatch")
            if any(
                not isinstance(value, (int, float)) or not math.isfinite(value)
                for vector in vectors
                for value in vector
            ):
                raise ValueError("non-finite embedding value")
            usage = body.get("usage", {})
            tokens = usage.get("prompt_tokens", usage.get("total_tokens", 0))
            if not isinstance(tokens, int) or tokens < 0:
                raise ValueError("invalid usage")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingError("invalid_provider_response") from error
        return EmbeddingBatch(
            model=self.model,
            vectors=[[float(value) for value in vector] for vector in vectors],
            input_tokens=tokens,
        )
