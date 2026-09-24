import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoints_are_honest_about_unconnected_services() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temp_dir) / "health.sqlite3")
        client = TestClient(create_app(settings))

        assert client.get("/api/health/live").json() == {"status": "alive"}
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "checks": {
                "application": "available",
                "database": "sqlite_available",
                "openalex": "not_connected",
                "llm": "disabled",
                "embedding": "disabled",
            },
        }


def test_readiness_reports_unavailable_when_sqlite_cannot_open() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temp_dir))
        response = TestClient(create_app(settings)).get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "unavailable"


def test_health_response_never_exposes_configured_secrets() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        settings = Settings(
            _env_file=None,
            data_storage_path=Path(temp_dir) / "health.sqlite3",
            openalex_api_key="openalex-secret",
            llm_provider="openai",
            llm_api_key="llm-secret",
            llm_model="example-model",
        )
        response = TestClient(create_app(settings)).get("/api/health/ready")

    assert "secret" not in response.text
    assert "example-model" not in response.text


def test_enabled_provider_requires_credentials_and_model() -> None:
    try:
        Settings(_env_file=None, llm_provider="openai")
    except ValueError as error:
        assert "LLM_API_KEY and LLM_MODEL" in str(error)
    else:
        raise AssertionError("enabled provider without credentials must be rejected")


def test_empty_optional_environment_values_are_treated_as_unset() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        env_file = Path(temp_dir) / ".env"
        env_file.write_text("EMBEDDING_DIMENSIONS=\n", encoding="utf-8")
        settings = Settings(_env_file=env_file)

    assert settings.embedding_dimensions is None
