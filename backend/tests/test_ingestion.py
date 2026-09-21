"""TEST-T03 synthetic=true throughout, with a dedicated disposable real PostgreSQL database."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.engine import make_url

from alembic import command
from app.catalog import models as catalog
from app.common.config import Settings
from app.ingestion import models as m
from app.ingestion.contracts import ImportInput, ImportRow, PublishInput, ReviewInput
from app.ingestion.service import ImportService, configuration_fingerprint, normalize
from app.main import create_app
from app.profiles.service import DomainError
from tools.synthetic_import import example

TOKEN = "TEST-ADMIN-" + "x" * 40
AUTH = json.dumps(
    {"operator_id": "TEST-OPERATOR", "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()}
)
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def database():
    supplied = os.environ.get("TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Set TEST_DATABASE_URL for real PostgreSQL tests")
    admin_url = make_url(supplied)
    assert (admin_url.database or "").startswith("test_")
    name = "test_t03_" + uuid4().hex

    def dsn(url):
        return url.set(drivername="postgresql").render_as_string(hide_password=False)

    with psycopg.connect(dsn(admin_url), autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = admin_url.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        redis_url="",
        session_signing_secret="TEST-SESSION-" + "x" * 40,
        admin_auth_config=AUTH,
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with pytest.MonkeyPatch.context() as env:
            env.setenv("DATABASE_URL", url)
            env.setenv("APP_ENV", "test")
            command.upgrade(config, "0003_catalog")
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            assert set(m.metadata.tables) <= set(inspect(engine).get_table_names())
            command.downgrade(config, "0003_catalog")
            assert set(catalog.metadata.tables) <= set(inspect(engine).get_table_names())
            command.upgrade(config, "head")
        yield engine, settings
    finally:
        engine.dispose()
        with psycopg.connect(dsn(admin_url), autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def service(database):
    engine, settings = database
    # Only fixed table names in this test module's disposable database; never user data.
    with engine.begin() as conn:
        names = list(m.metadata.tables) + list(catalog.metadata.tables) + ["request_limits"]
        conn.execute(text("TRUNCATE " + ",".join(names)))
    return ImportService(engine, settings, "TEST-OPERATOR", clock=lambda: NOW)


def batch(value=None):
    return ImportInput.model_validate(value or example())


def request_for(job, **changes):
    return dict(content_hash=job.content_hash, base_version=job.preview.base_version, **changes)


def approve(service, job, selected=None):
    return service.review(
        job.id,
        ReviewInput(
            **request_for(
                job,
                decision="approve",
                note="TEST manually checked source and identity",
                selected_fact_ids=selected or [],
            )
        ),
    )


def publish(service, job):
    return service.publish(job.id, PublishInput(**request_for(job)))


def counts(service):
    with service.engine.connect() as conn:
        return {
            table.name: conn.scalar(select(func.count()).select_from(table))
            for table in list(m.metadata.tables.values()) + list(catalog.metadata.tables.values())
        }


def row(value, kind):
    return next(item["data"] for item in value["rows"] if item["kind"] == kind)


@pytest.mark.integration
def test_preview_stage_review_publish_and_notification(service):
    before = counts(service)
    preview = service.preview(batch())
    assert preview.valid and preview.publishable, preview.issues
    assert counts(service) == before
    assert all(item.action == "add" for item in preview.rows)
    job = service.stage(batch())
    assert job.status == "staged" and service.stage(batch()).id == job.id
    assert service.get(job.id).checkpoint == "validated"
    assert counts(service)["product_skus"] == 0
    with pytest.raises(DomainError, match="只有已批准"):
        publish(service, job)
    reviewed = approve(service, job)
    assert reviewed.reviewer == "TEST-OPERATOR"
    result = publish(service, reviewed)
    assert publish(service, reviewed) == result
    assert service.stage(batch()).status == "published"
    after = counts(service)
    assert after["dataset_versions"] == after["publication_outbox"] == after["canonical_specs"] == 1
    with service.engine.connect() as conn:
        assert (
            conn.scalar(select(m.pointers.c.version_id).where(m.pointers.c.synthetic.is_(False)))
            is None
        )
        assert conn.scalar(select(catalog.evidence.c.review_status)) == "approved"
        assert conn.scalar(select(catalog.offers.c.amount_minor)) == 123456
    assert service.dispatch() == {"delivered": 1, "failed": 0}
    assert service.dispatch() == {"delivered": 0, "failed": 0}


@pytest.mark.integration
@pytest.mark.parametrize(
    "kind,changes,code",
    [
        (
            "sources",
            {"permission_status": "unknown", "allowed_uses": []},
            "SOURCE_PERMISSION_REQUIRED",
        ),
        ("product_skus", {"identity_status": "pending"}, "SKU_IDENTITY_PENDING"),
        ("offer_snapshots", {"amount_minor": -1}, "INVALID_RECORD"),
        ("offer_snapshots", {"amount_minor": 1.2}, "INVALID_RECORD"),
        ("spec_facts", {"unit": "MHz"}, "RELATION_OR_CONSTRAINT"),
        ("spec_facts", {"evidence_id": str(uuid4())}, "RELATION_OR_CONSTRAINT"),
        ("source_documents", {"source_id": str(uuid4())}, "RELATION_OR_CONSTRAINT"),
        ("source_documents", {"fetched_at": "2099-01-01T00:00:00Z"}, "FUTURE_OBSERVATION"),
        (
            "evidence",
            {"review_status": "approved", "reviewer": "forged"},
            "CLIENT_REVIEW_FORBIDDEN",
        ),
        ("offer_snapshots", {"synthetic": False}, "INVALID_RECORD"),
        ("source_documents", {"storage_key": "unverified/raw.txt"}, "RAW_STORAGE_NOT_SUPPORTED"),
    ],
)
def test_bad_batch_never_changes_published_version(service, kind, changes, code):
    value = example()
    row(value, kind).update(changes)
    job = service.stage(batch(value))
    assert code in {issue.code for issue in job.preview.issues}
    with pytest.raises(DomainError):
        approve(service, job)
    with pytest.raises(DomainError):
        publish(service, job)
    assert counts(service)["dataset_versions"] == counts(service)["product_skus"] == 0


@pytest.mark.integration
def test_hash_idempotency_and_read_only_existing_records(service):
    job = service.stage(batch())
    changed = example()
    row(changed, "spec_facts")["value_integer"] = 12
    with pytest.raises(DomainError) as error:
        service.stage(batch(changed))
    assert error.value.code == "BATCH_KEY_REUSED"
    approve(service, job)
    publish(service, job)
    changed["external_batch_id"] = "TEST-CHANGED"
    blocked = service.stage(batch(changed))
    assert "IMMUTABLE_RECORD_CONFLICT" in {issue.code for issue in blocked.preview.issues}
    assert counts(service)["dataset_versions"] == 1
    replay = example()
    replay["external_batch_id"] = "TEST-UNCHANGED"
    preview = service.preview(batch(replay))
    assert all(item.action == "unchanged" for item in preview.rows)


@pytest.mark.integration
def test_conflicting_facts_require_explicit_selection_and_keep_history(service):
    value = example()
    original = row(value, "spec_facts")
    other = {
        **original,
        "id": str(uuid4()),
        "record_key": "TEST-ALTERNATE",
        "value_integer": 12,
        "raw_value": "12",
    }
    value["rows"].append({"kind": "spec_facts", "data": other})
    job = service.stage(batch(value))
    assert job.preview.valid and not job.preview.publishable
    with pytest.raises(DomainError) as error:
        approve(service, job)
    assert error.value.code == "UNRESOLVED_CONFLICT"
    approve(service, job, [other["id"]])
    publish(service, job)
    with service.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(catalog.facts)) == 2
        assert conn.scalar(select(m.canonical.c.value_integer)) == 12


@pytest.mark.integration
def test_atomic_rollback_and_retry(service, monkeypatch):
    job = service.stage(batch())
    approve(service, job)
    before = counts(service)
    original = service._enqueue

    def fail(*args):
        raise RuntimeError("TEST failure after pointer update")

    monkeypatch.setattr(service, "_enqueue", fail)
    with pytest.raises(RuntimeError):
        publish(service, job)
    assert counts(service) == before
    assert service.get(job.id).status == "approved"
    monkeypatch.setattr(service, "_enqueue", original)
    publish(service, job)
    assert counts(service)["dataset_versions"] == 1


@pytest.mark.integration
def test_concurrent_publish_and_stale_parent(service):
    first = service.stage(batch())
    value = example()
    value["external_batch_id"] = "TEST-SECOND"
    second = service.stage(batch(value))
    approve(service, first)
    approve(service, second)

    def run(job):
        try:
            return publish(service, job)
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [first, second]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "DATA_VERSION_CHANGED" in results
    assert counts(service)["dataset_versions"] == 1


@pytest.mark.integration
def test_outbox_retry_lease_recovery_and_idempotence(service):
    job = service.stage(batch())
    approve(service, job)
    publish(service, job)

    def fail(_):
        raise RuntimeError("TEST failure; never persisted")

    assert service.dispatch(consumer=fail) == {"delivered": 0, "failed": 1}
    assert service.dispatch() == {"delivered": 0, "failed": 0}
    service.clock = lambda: NOW + timedelta(seconds=60)
    with service.engine.begin() as conn:
        conn.execute(update(m.outbox).values(status="leased", lease_id=uuid4(), lease_until=NOW))
    assert service.dispatch() == {"delivered": 1, "failed": 0}
    assert counts(service)["dataset_notifications"] == 1


def test_fingerprint_is_order_stable_and_preserves_configuration_difference():
    value = {key: "TEST-" + key for key in ["cpu", "gpu", "memory", "storage", "display"]}
    assert configuration_fingerprint(value) == configuration_fingerprint(
        dict(reversed(list(value.items())))
    )
    assert configuration_fingerprint(value) != configuration_fingerprint(
        value | {"display": "TEST-other"}
    )
    with pytest.raises(ValueError):
        configuration_fingerprint({"cpu": "TEST-only"})


@pytest.mark.integration
@pytest.mark.parametrize(
    "environment,dbname",
    [("production", "test_t03"), ("development", "test_t03"), ("test", "computer")],
)
def test_synthetic_rejected_outside_test_environment_and_database(service, environment, dbname):
    settings = service.settings.model_copy(update={"app_env": environment})
    url = make_url(settings.database_url.get_secret_value()).set(database=dbname)
    from pydantic import SecretStr

    settings.database_url = SecretStr(url.render_as_string(hide_password=False))
    isolated = ImportService(service.engine, settings, "TEST-OPERATOR")
    with pytest.raises(DomainError) as error:
        isolated.preview(batch())
    assert error.value.code == "SYNTHETIC_FORBIDDEN"


@pytest.mark.integration
def test_admin_auth_origin_size_and_complete_http_flow(service):
    headers = {"Authorization": "Bearer " + TOKEN}
    with TestClient(create_app(service.settings)) as client:
        assert client.post("/api/v1/admin/imports", json=example()).status_code == 401
        assert client.get("/api/v1/admin/imports/" + str(uuid4())).status_code == 401
        assert (
            client.post(
                "/api/v1/admin/imports",
                headers=headers | {"Origin": "https://evil.example"},
                json=example(),
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/admin/imports",
                headers=headers | {"Content-Type": "application/json"},
                content=" " * 1048577,
            ).status_code
            == 413
        )
        assert (
            client.post("/api/v1/admin/imports", headers=headers, content="{}").status_code == 415
        )
        preview = client.post("/api/v1/admin/imports/preview", headers=headers, json=example())
        assert preview.status_code == 200 and preview.json()["valid"]
        response = client.post("/api/v1/admin/imports", headers=headers, json=example())
        assert response.status_code == 200, response.text
        job = response.json()
        decision = dict(
            content_hash=job["content_hash"],
            base_version=job["preview"]["base_version"],
            decision="approve",
            note="TEST review",
        )
        reviewed = client.post(
            f"/api/v1/admin/imports/{job['id']}/review", headers=headers, json=decision
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["reviewer"] == "TEST-OPERATOR"
        published = client.post(
            f"/api/v1/admin/imports/{job['id']}/publish",
            headers=headers,
            json={k: decision[k] for k in ("content_hash", "base_version")},
        )
        assert published.status_code == 200, published.text
        assert client.get("/api/v1/platform/status").json()["recommendation_available"] is False
        assert TOKEN not in json.dumps(job)


@pytest.mark.integration
def test_review_hash_and_forbidden_reviewer_input(service):
    job = service.stage(batch())
    with pytest.raises(DomainError) as error:
        service.review(
            job.id,
            ReviewInput(
                **request_for(job, decision="approve", note="TEST note")
                | {"content_hash": "a" * 64}
            ),
        )
    assert error.value.code == "STALE_REVIEW"
    with TestClient(create_app(service.settings)) as client:
        response = client.post(
            f"/api/v1/admin/imports/{job.id}/review",
            headers={"Authorization": "Bearer " + TOKEN},
            json={
                "content_hash": job.content_hash,
                "base_version": None,
                "decision": "approve",
                "note": "TEST",
                "reviewer": "forged",
            },
        )
        assert response.status_code == 422


@pytest.mark.integration
def test_second_version_bad_batch_and_old_snapshot_remain_unchanged(service):
    first = service.stage(batch())
    approve(service, first)
    initial = publish(service, first)
    with service.engine.connect() as conn:
        original = conn.scalar(select(m.versions.c.records))
    value = example()
    value["external_batch_id"] = "TEST-NEW-QUOTE"
    quote = dict(row(value, "offer_snapshots"))
    quote.update(id=str(uuid4()), record_key="TEST-NEW-QUOTE", amount_minor=150000)
    value["rows"] = [{"kind": "offer_snapshots", "data": quote}]
    second = service.stage(batch(value))
    assert second.preview.base_version == initial["version_id"]
    approve(service, second)
    result = publish(service, second)
    assert result["version_id"] != initial["version_id"]
    bad = example()
    bad["external_batch_id"] = "TEST-BAD-AFTER-PUBLISH"
    row(bad, "spec_facts")["unit"] = "MHz"
    bad_job = service.stage(batch(bad))
    with pytest.raises(DomainError):
        approve(service, bad_job)
    with service.engine.connect() as conn:
        assert conn.scalar(select(m.pointers.c.version_id)) == result["version_id"]
        assert (
            conn.scalar(
                select(m.versions.c.records).where(m.versions.c.id == initial["version_id"])
            )
            == original
        )
        assert conn.scalar(select(func.count()).select_from(catalog.offers)) == 2


@pytest.mark.integration
def test_reject_and_concurrent_stage_retry(service):
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda _: service.stage(batch()), range(2)))
    assert jobs[0].id == jobs[1].id
    job = jobs[0]
    service.review(
        job.id, ReviewInput(**request_for(job, decision="reject", note="TEST rejected evidence"))
    )
    with pytest.raises(DomainError):
        publish(service, job)
    with pytest.raises(DomainError):
        approve(service, job)


@pytest.mark.integration
def test_snapshot_drift_blocks_next_publication(service):
    job = service.stage(batch())
    approve(service, job)
    publish(service, job)
    with service.engine.begin() as conn:
        conn.execute(update(catalog.facts).values(value_integer=99))
    value = example()
    value["external_batch_id"] = "TEST-DRIFT"
    preview = service.preview(batch(value))
    assert "PUBLISHED_RECORD_DRIFT" in {issue.code for issue in preview.issues}


@pytest.mark.parametrize(
    "raw_unit,unit,raw_value,value,allowed",
    [
        ("cm", "mm", "12.5", "125", True),
        ("kg", "g", "1.25", "1250", True),
        ("cm", "mm", "12.5", "12.5", False),
        ("MHz", "MT/s", "1600", "3200", False),
        ("GB", "GiB", "1024", "1024", False),
    ],
)
def test_unit_conversion_is_explicit_and_exact(raw_unit, unit, raw_value, value, allowed):
    data = row(example(), "spec_facts")
    data.update(
        value_integer=None,
        value_type="decimal",
        value_decimal=value,
        raw_unit=raw_unit,
        unit=unit,
        raw_value=raw_value,
    )
    supplied = ImportRow(kind="spec_facts", data=data)
    if allowed:
        assert str(normalize(supplied, {}).value_decimal) == value
    else:
        with pytest.raises(ValueError):
            normalize(supplied, {})


@pytest.mark.integration
def test_cli_full_flow_in_isolated_database(service, tmp_path):
    env = os.environ | {
        "APP_ENV": "test",
        "DATABASE_URL": service.settings.database_url.get_secret_value(),
        "ADMIN_AUTH_CONFIG": AUTH,
        "ADMIN_TOKEN": TOKEN,
        "REDIS_URL": "",
    }
    source_file = tmp_path / "TEST-batch.json"
    source_file.write_text(json.dumps(example()), encoding="utf-8")

    def run(*args):
        result = subprocess.run(
            [sys.executable, "-m", "tools.import_catalog", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout
        assert TOKEN not in result.stdout + result.stderr
        return json.loads(result.stdout)

    assert run("stage", "--dry-run", "--file", str(source_file))["valid"]
    assert counts(service)["ingestion_jobs"] == 0
    job = run("stage", "--file", str(source_file))
    assert run("resume", "--job", job["id"])["checkpoint"] == "validated"
    request_file = tmp_path / "TEST-review.json"
    review = dict(
        content_hash=job["content_hash"],
        base_version=job["preview"]["base_version"],
        decision="approve",
        note="TEST CLI review",
    )
    request_file.write_text(json.dumps(review), encoding="utf-8")
    assert run("review", "--job", job["id"], "--file", str(request_file))["status"] == "approved"
    request_file.write_text(
        json.dumps({k: review[k] for k in ("content_hash", "base_version")}), encoding="utf-8"
    )
    assert run("publish", "--job", job["id"], "--file", str(request_file))["synthetic"] is True
    assert run("dispatch")["delivered"] == 1


@pytest.mark.integration
def test_admin_write_rate_limit_and_invalid_config_fail_closed(service):
    from app.profiles.service import ProfileService

    limiter = ProfileService(service.engine, service.settings)
    for _ in range(30):
        limiter.rate_limit("admin:TEST-OPERATOR", 30)
    with TestClient(create_app(service.settings)) as client:
        response = client.post(
            "/api/v1/admin/imports/preview",
            headers={"Authorization": "Bearer " + TOKEN},
            json=example(),
        )
        assert response.status_code == 429
    from pydantic import SecretStr

    settings = service.settings.model_copy(update={"admin_auth_config": SecretStr("not-json")})
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/admin/imports/" + str(uuid4())).status_code == 503


@pytest.mark.integration
def test_price_jump_is_visible_and_real_dispatch_does_not_consume_synthetic(service):
    first = service.stage(batch())
    approve(service, first)
    publish(service, first)
    value = example()
    quote = row(value, "offer_snapshots")
    quote.update(id=str(uuid4()), record_key="TEST-JUMP", amount_minor=300000)
    value.update(external_batch_id="TEST-JUMP", rows=[{"kind": "offer_snapshots", "data": quote}])
    preview = service.preview(batch(value))
    assert "PRICE_CHANGE_REVIEW" in {issue.code for issue in preview.issues}
    real_settings = service.settings.model_copy(update={"app_env": "development"})
    assert (
        ImportService(service.engine, real_settings, "TEST-OPERATOR").dispatch()["delivered"] == 0
    )
    assert service.dispatch()["delivered"] == 1


@pytest.mark.integration
def test_unpublished_database_record_cannot_implicitly_join_version(service):
    from app.catalog.contracts import CatalogAttribute

    first = service.stage(batch())
    approve(service, first)
    publish(service, first)
    value = example()
    attribute = row(value, "attribute_definitions")
    attribute.update(id=str(uuid4()), record_key="TEST-UNPUBLISHED", key="test_unpublished")
    with service.engine.begin() as conn:
        conn.execute(
            catalog.attributes.insert().values(
                **CatalogAttribute.model_validate(attribute).model_dump()
            )
        )
    fact = row(value, "spec_facts")
    fact.update(id=str(uuid4()), record_key="TEST-ORPHAN", attribute_id=attribute["id"])
    value.update(external_batch_id="TEST-ORPHAN", rows=[{"kind": "spec_facts", "data": fact}])
    preview = service.preview(batch(value))
    assert preview.valid and not preview.publishable
    assert "UNPUBLISHED_REFERENCE" in {issue.code for issue in preview.issues}
