import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic.config import Config
from fastapi import Response
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url

from alembic import command
from app.common.config import Settings
from app.main import create_app
from app.profiles.contracts import ProfileInput, ProfilePatch
from app.profiles.models import profiles, revisions, sessions
from app.profiles.router import set_cookie
from app.profiles.service import DomainError, ProfileService

ORIGIN = "http://localhost:3000"
# Scenario metadata is separate from the strict production profile request schema.
CASE_METADATA = {"case_id": "TEST-I02-PROFILE", "synthetic": True}
BASE = {
    "mode": "pc",
    "budget_max_minor": 600001,
    "workloads": ["gaming"],
    "budget_scope": ["tower"],
    "excluded_brands": ["TEST-BRAND"],
    "pc_constraints": {"wifi_required": True},
}


@pytest.fixture(scope="module")
def database():
    supplied = os.environ.get("TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Requires real TEST_DATABASE_URL")
    admin_url = make_url(supplied)
    assert admin_url.database.startswith("test_")
    name = "test_i02_" + uuid4().hex

    def dsn(url):
        return url.set(drivername="postgresql").render_as_string(hide_password=False)

    with psycopg.connect(dsn(admin_url), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = admin_url.set(database=name).render_as_string(hide_password=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        redis_url="",
        session_signing_secret="test-only-secret-" + "x" * 32,
    )
    engine = create_engine(url)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            patch.setenv("APP_ENV", "test")
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "0001_baseline")
            with TestClient(create_app(settings)) as client:
                assert client.get("/api/v1/health/ready").status_code == 503
            command.upgrade(config, "head")
            command.upgrade(config, "head")
        yield settings, engine
    finally:
        engine.dispose()
        with psycopg.connect(dsn(admin_url), autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def client(database):
    with TestClient(create_app(database[0])) as client:
        yield client


def bootstrap(client):
    response = client.post("/api/v1/sessions", json={}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def save(client, headers, body=None):
    response = client.post("/api/v1/profiles", json=BASE if body is None else body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("budget", [True, False, 6000.1, "600000", 0, -1, 1000000001, None])
def test_budget_is_strict_integer_minor_units(budget):
    with pytest.raises(ValidationError):
        ProfileInput.model_validate({**BASE, "budget_max_minor": budget})


def test_secure_cookie_flags():
    config = Settings(_env_file=None).model_copy(update={"app_env": "production"})
    response = Response()
    set_cookie(response, "test-cookie", config)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-computer_session=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Max-Age=86400" in cookie and "Path=/" in cookie and "Domain=" not in cookie


@pytest.mark.integration
def test_saved_profile_history_and_partial_patch(client, database):
    headers = bootstrap(client)
    cookie = client.cookies.get("computer_session")
    again = client.post("/api/v1/sessions", json={}, headers={"Origin": ORIGIN})
    assert again.json()["csrf_token"] == headers["X-CSRF-Token"]
    assert "set-cookie" not in again.headers  # no sliding TTL or rotation on refresh
    first = save(client, headers)
    assert first["revision"] == 1
    assert first["origins"]["budget_max_minor"]["origin"] == "explicit"
    assert first["origins"]["market"]["origin"] == "default"
    assert first["profile"]["budget_max_minor"] == 600001
    assert client.get("/api/v1/sessions/current").json()["profile"] == first
    response = client.patch(
        f"/api/v1/profiles/{first['id']}",
        headers=headers,
        json={"expected_revision": 1, "patch": {"workloads": ["development"]}},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["revision"] == 2
    assert updated["profile"]["excluded_brands"] == ["TEST-BRAND"]
    assert updated["profile"]["budget_max_minor"] == 600001
    assert updated["profile"]["pc_constraints"] == {"wifi_required": True}
    assert updated["origins"]["budget_max_minor"] == first["origins"]["budget_max_minor"]
    assert client.get(f"/api/v1/profiles/{first['id']}/revisions/1").json() == first
    assert client.post("/api/v1/profiles", json=BASE, headers=headers).status_code == 409
    with database[1].connect() as conn:
        stored = conn.execute(select(sessions.c.token_hash)).scalars().all()
        assert cookie not in stored and all(len(value) == 64 for value in stored)


@pytest.mark.integration
def test_origins_csrf_json_and_size_guards(client):
    for origin in (None, "null", "http://localhost:3000.evil.example", "https://evil.example"):
        assert (
            client.post(
                "/api/v1/sessions", json={}, headers={"Origin": origin} if origin else {}
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/v1/sessions",
            content="{}",
            headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    response = client.post(
        "/api/v1/sessions",
        content=b"x" * 16385,
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    headers = bootstrap(client)
    for token in ("", "forged"):
        assert (
            client.post(
                "/api/v1/profiles", json=BASE, headers={"Origin": ORIGIN, "X-CSRF-Token": token}
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/v1/profiles", json=BASE, headers={**headers, "Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/profiles", json={**BASE, "owner_id": str(uuid4())}, headers=headers
        ).status_code
        == 422
    )
    save(client, headers)


@pytest.mark.integration
def test_cross_session_invisible_and_forged_cookie(client, database):
    own_headers = bootstrap(client)
    first = save(client, own_headers)
    with TestClient(create_app(database[0])) as other:
        headers = bootstrap(other)
        for path in (
            f"/api/v1/profiles/{first['id']}",
            f"/api/v1/profiles/{first['id']}/revisions/1",
        ):
            assert other.get(path).status_code == 404
        assert (
            other.patch(
                f"/api/v1/profiles/{first['id']}",
                headers=headers,
                json={"expected_revision": 1, "patch": {"budget_max_minor": 1}},
            ).status_code
            == 404
        )
        assert other.post("/api/v1/profiles", json=BASE, headers=own_headers).status_code == 403
        other.cookies.set("computer_session", "forged.invalid", domain="testserver.local", path="/")
        assert other.get(f"/api/v1/profiles/{first['id']}").status_code == 404


@pytest.mark.integration
def test_mode_switch_clears_only_device_fields(client):
    headers = bootstrap(client)
    first = save(client, headers)
    path = f"/api/v1/profiles/{first['id']}"
    response = client.patch(
        path, headers=headers, json={"expected_revision": 1, "patch": {"mode": "laptop"}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["pc_constraints"] is None
    assert body["profile"]["budget_scope"] == ["laptop"]
    assert body["profile"]["budget_max_minor"] == 600001
    assert body["profile"]["excluded_brands"] == ["TEST-BRAND"]
    assert body["origins"]["budget_scope"]["origin"] == "default"
    # Invalid null/empty patches never consume a revision.
    for patch in (
        {"budget_max_minor": None},
        {"mode": None},
        {},
        {"pc_constraints": {"wifi_required": True}},
    ):
        assert (
            client.patch(
                path, headers=headers, json={"expected_revision": 2, "patch": patch}
            ).status_code
            == 422
        )
    assert client.get(path).json()["revision"] == 2


@pytest.mark.integration
def test_atomic_concurrent_revision(client, database):
    headers = bootstrap(client)
    first = save(client, headers)
    service = ProfileService(database[1], database[0])
    cookie = client.cookies.get("computer_session")

    def attempt(amount):
        try:
            return service.save(
                cookie, ProfilePatch(budget_max_minor=amount), UUID(first["id"]), 1
            ).revision
        except DomainError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [500001, 500002]))
    assert sorted(results) == [2, 409]
    assert client.get(f"/api/v1/profiles/{first['id']}/revisions/1").json() == first


@pytest.mark.integration
def test_reset_and_delete_revoke_old_identity_and_cascade(client, database):
    headers = bootstrap(client)
    first = save(client, headers)
    old_cookie = client.cookies.get("computer_session")
    response = client.post("/api/v1/sessions/reset", json={}, headers=headers)
    assert response.status_code == 200 and response.json()["profile"] is None
    assert client.cookies.get("computer_session") != old_cookie
    assert client.get(f"/api/v1/profiles/{first['id']}").status_code == 404
    with TestClient(create_app(database[0])) as stale:
        stale.cookies.set("computer_session", old_cookie)
        assert stale.get("/api/v1/sessions/current").status_code == 404
    new_headers = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}
    second = save(client, new_headers)
    assert (
        client.request(
            "DELETE", "/api/v1/sessions/current", json={}, headers=new_headers
        ).status_code
        == 204
    )
    assert client.get("/api/v1/sessions/current").status_code == 404
    with database[1].connect() as conn:
        ids = [UUID(first["id"]), UUID(second["id"])]
        assert (
            conn.scalar(
                select(func.count()).select_from(revisions).where(revisions.c.profile_id.in_(ids))
            )
            == 0
        )


@pytest.mark.integration
def test_expiry_and_cleanup(client, database):
    headers = bootstrap(client)
    first = save(client, headers)
    with database[1].begin() as conn:
        owner = conn.scalar(select(profiles.c.session_id).where(profiles.c.id == UUID(first["id"])))
        conn.execute(
            update(sessions)
            .where(sessions.c.id == owner)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert client.get("/api/v1/sessions/current").status_code == 404
    assert (
        client.patch(
            f"/api/v1/profiles/{first['id']}",
            headers=headers,
            json={"expected_revision": 1, "patch": {"budget_max_minor": 1}},
        ).status_code
        == 404
    )
    assert ProfileService(database[1], database[0]).cleanup() >= 1
    with database[1].connect() as conn:
        assert conn.scalar(select(profiles.c.id).where(profiles.c.id == UUID(first["id"]))) is None


@pytest.mark.integration
def test_shared_limit_and_dependency_fail_closed(database):
    config = database[0].model_copy(update={"session_write_limit": 1})
    with TestClient(create_app(config), client=("rate-limit-test", 50000)) as client:
        headers = bootstrap(client)
        save(client, headers)
        response = client.post("/api/v1/sessions/reset", json={}, headers=headers)
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    broken = Settings(
        _env_file=None,
        app_env="test",
        database_url=config.database_url,
        redis_url="redis://127.0.0.1:1",
        session_signing_secret=config.session_signing_secret,
    )
    with TestClient(create_app(broken)) as client:
        response = client.post("/api/v1/sessions", json={}, headers={"Origin": ORIGIN})
        assert response.status_code == 503
        assert "redis://" not in response.text
