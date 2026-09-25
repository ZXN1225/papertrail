from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.openalex import OpenAlexPage


def test_search_route_passes_key_only_to_server_client(monkeypatch) -> None:
    passed_keys: list[str | None] = []

    class FakeOpenAlexClient:
        def __init__(self, api_key: str | None = None) -> None:
            passed_keys.append(api_key)

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def search_works(
            self,
            query: str,
            *,
            page: int,
            per_page: int,
            from_year: int | None,
            to_year: int | None,
        ) -> OpenAlexPage:
            assert (query, page, per_page, from_year, to_year) == (
                "agent research",
                1,
                10,
                2022,
                2024,
            )
            return OpenAlexPage.model_validate(
                {
                    "meta": {"count": 0, "page": page, "per_page": per_page},
                    "results": [],
                    "fetched_at": "2026-09-23T00:00:00Z",
                }
            )

    monkeypatch.setattr("app.main.OpenAlexClient", FakeOpenAlexClient)
    client = TestClient(create_app(Settings(_env_file=None, openalex_api_key="test-openalex-key")))

    response = client.get("/api/v1/papers/search?q=agent%20research&from_year=2022&to_year=2024")

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 0
    assert "test-openalex-key" not in response.text
    assert passed_keys == ["test-openalex-key"]


def test_search_route_rejects_invalid_query_before_source_request(monkeypatch) -> None:
    def must_not_construct(**_kwargs):
        raise AssertionError("invalid query must be rejected before contacting the source")

    monkeypatch.setattr("app.main.OpenAlexClient", must_not_construct)
    client = TestClient(create_app(Settings(_env_file=None)))

    response = client.get("/api/v1/papers/search?q=%20%20%20")

    assert response.status_code == 422
