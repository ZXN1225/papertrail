import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from alembic import command
from app.common.config import Settings
from app.main import create_app


def settings(**overrides):
    return Settings(_env_file=None, app_env="test", database_url="", redis_url="", **overrides)


def test_live_is_independent_but_ready_requires_database():
    with TestClient(create_app(settings())) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "alive"}
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["database"] == "not_configured"
        response = client.get("/api/v1/platform/status")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]
        assert response.headers["Cache-Control"] == "no-store"
        assert client.post("/api/v1/admin/imports").status_code == 404


def test_database_outage_is_503_and_does_not_leak_credentials():
    config = Settings(
        _env_file=None,
        app_env="test",
        redis_url="",
        database_url="postgresql+psycopg://private_user:private_secret@127.0.0.1:1/missing",
    )
    with TestClient(create_app(config)) as client:
        for path in ("/api/v1/health/ready", "/api/v1/platform/status"):
            response = client.get(path)
            assert response.status_code == 503
            assert "private_secret" not in response.text
            assert "private_user" not in response.text
        assert client.get("/api/v1/health/live").status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"database_url": "postgresql+psycopg://u:p@localhost/db"},
        {
            "database_url": "postgresql+psycopg://u:p@localhost/db",
            "redis_url": "redis://localhost:6379",
        },
        {
            "database_url": "postgresql+psycopg://u:p@localhost/db",
            "redis_url": "redis://localhost:6379",
            "session_signing_secret": "x" * 32,
            "public_base_url": "http://localhost:3000",
        },
    ],
)
def test_production_rejects_incomplete_or_insecure_config(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", **overrides)


def test_production_validates_without_connecting_or_enabling_llm():
    config = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://u:p@localhost/db",
        redis_url="redis://localhost:6379",
        session_signing_secret="x" * 32,
        public_base_url="https://example.com",
        cors_allowed_origins="https://example.com",
    )
    assert config.llm_provider == "disabled"


@pytest.mark.parametrize(
    "values",
    [
        {"database_url": "sqlite:///fake.db"},
        {"cors_allowed_origins": "*"},
        {"redis_url": "https://example.com"},
        {"llm_provider": "openai"},
    ],
)
def test_invalid_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_cors_accepts_only_explicit_origin():
    with TestClient(create_app(settings())) as client:
        allowed = client.get("/api/v1/health/live", headers={"Origin": "http://localhost:3000"})
        denied = client.get("/api/v1/health/live", headers={"Origin": "https://untrusted.example"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-origin" not in denied.headers


@pytest.mark.integration
def test_real_postgres_empty_migration_and_dependency_failures(monkeypatch):
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Set TEST_DATABASE_URL explicitly to a test_* PostgreSQL database")
    admin_url = make_url(test_url)
    if not (admin_url.database or "").startswith("test_"):
        pytest.fail("TEST_DATABASE_URL must identify a test_* database")
    database = "test_i01_" + uuid4().hex

    def dsn(url):
        return url.set(drivername="postgresql").render_as_string(hide_password=False)

    with psycopg.connect(dsn(admin_url), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    isolated_url = admin_url.set(database=database).render_as_string(hide_password=False)
    config = Settings(_env_file=None, app_env="test", database_url=isolated_url, redis_url="")
    try:
        with TestClient(create_app(config)) as client:
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 503
            assert response.json()["checks"]["database"] == "migration_required"
        monkeypatch.setenv("DATABASE_URL", isolated_url)
        monkeypatch.setenv("APP_ENV", "test")
        alembic = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(alembic, "head")
        command.upgrade(alembic, "head")  # Repeat is safe and does not seed product data.
        with TestClient(create_app(config)) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
            body = client.get("/api/v1/platform/status").json()
            assert body["data_status"] == "not_initialized"
            assert body["recommendation_available"] is False
            assert body["data_version"] is None
            assert body["mode"] == "deterministic"
        redis_test = os.environ.get("TEST_REDIS_URL")
        if redis_test:
            with TestClient(
                create_app(
                    config.model_copy(
                        update={
                            "redis_url": Settings(_env_file=None, redis_url=redis_test).redis_url,
                        }
                    )
                )
            ) as client:
                response = client.get("/api/v1/health/ready")
                assert response.status_code == 200
                assert response.json()["checks"]["redis"] == "ready"
        elif os.environ.get("CI"):
            pytest.fail("CI must set TEST_REDIS_URL for the real Redis check")
        broken_redis = Settings(
            _env_file=None,
            app_env="test",
            database_url=isolated_url,
            redis_url="redis://127.0.0.1:1",
        )
        with TestClient(create_app(broken_redis)) as client:
            assert client.get("/api/v1/health/ready").status_code == 503
            assert client.get("/api/v1/platform/status").status_code == 503
        command.downgrade(alembic, "base")
        with TestClient(create_app(config)) as client:
            assert client.get("/api/v1/health/ready").status_code == 503
        command.upgrade(alembic, "head")
    finally:
        # Drop only our unique test database, never the supplied database.
        with psycopg.connect(dsn(admin_url), autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
