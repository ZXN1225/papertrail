from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.embeddings.client import EmbeddingError, OpenAIEmbeddingClient
from app.retrieval.vectors import cosine_similarity, dense_rank, reciprocal_rank_fusion


def _settings(**kwargs) -> Settings:
    return Settings(
        _env_file=None,
        embedding_provider="openai",
        embedding_api_key="unit-test-secret",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=3,
        **kwargs,
    )


def test_openai_embedding_client_sends_bounded_fixed_host_request_and_orders_results() -> None:
    observed = {}

    def respond(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["authorization"]
        observed["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-small",
                "data": [
                    {"index": 1, "embedding": [0, 1, 0]},
                    {"index": 0, "embedding": [1, 0, 0]},
                ],
                "usage": {"prompt_tokens": 9},
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(respond))
    client = OpenAIEmbeddingClient(_settings(), http_client=http)
    batch = client.embed(["first", "second"])
    assert observed["url"] == "https://api.openai.com/v1/embeddings"
    assert observed["authorization"] == "Bearer unit-test-secret"
    assert '"dimensions":3' in observed["body"]
    assert batch.vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert batch.input_tokens == 9
    http.close()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"model": "text-embedding-3-small", "data": [], "usage": {}}, "invalid_provider_response"),
        (
            {
                "model": "text-embedding-3-small",
                "data": [{"index": 0, "embedding": [1, 2]}],
                "usage": {},
            },
            "invalid_provider_response",
        ),
    ],
)
def test_openai_embedding_client_rejects_invalid_provider_response(payload, code: str) -> None:
    http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    client = OpenAIEmbeddingClient(_settings(), http_client=http)
    with pytest.raises(EmbeddingError, match=code):
        client.embed(["test"])
    http.close()


def test_openai_embedding_client_classifies_auth_rate_limit_and_timeout() -> None:
    for status, expected in (
        (401, "authentication_failed"),
        (429, "rate_limited"),
        (503, "provider_unavailable"),
    ):
        http = httpx.Client(
            transport=httpx.MockTransport(lambda request, status=status: httpx.Response(status))
        )
        client = OpenAIEmbeddingClient(_settings(), http_client=http)
        with pytest.raises(EmbeddingError, match=expected):
            client.embed(["test"])
        http.close()

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private detail", request=request)

    http = httpx.Client(transport=httpx.MockTransport(timeout))
    client = OpenAIEmbeddingClient(_settings(), http_client=http)
    with pytest.raises(EmbeddingError, match="timeout"):
        client.embed(["test"])
    http.close()


def test_embedding_client_validates_input_bounds_and_cosine_ranking() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    client = OpenAIEmbeddingClient(_settings(), http_client=http)
    with pytest.raises(EmbeddingError, match="invalid_batch_size"):
        client.embed([])
    with pytest.raises(EmbeddingError, match="empty_input"):
        client.embed(["  "])
    with pytest.raises(EmbeddingError, match="input_too_large"):
        client.embed(["x" * 8_001])
    assert cosine_similarity([1, 0], [0, 4]) == 0
    assert dense_rank([0, 1], {"a": [1, 0], "b": [0, 1]}) == [("b", 1.0), ("a", 0.0)]
    assert reciprocal_rank_fusion([["a", "b"], ["b", "a"]]) == [
        ("a", 0.03252247488101534),
        ("b", 0.03252247488101534),
    ]
    with pytest.raises(ValueError, match="same positive dimension"):
        cosine_similarity([1], [1, 2])
    http.close()
