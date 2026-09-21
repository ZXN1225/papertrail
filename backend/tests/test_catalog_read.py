"""T04/T05 only uses synthetic TEST records in an isolated disposable PostgreSQL database."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from alembic import command
from app.catalog.read_service import CatalogReadService, PriceService
from app.common.config import Settings
from app.ingestion.contracts import ImportInput, PublishInput, ReviewInput
from app.ingestion.service import ImportService
from app.main import create_app
from app.profiles.service import DomainError
from tools.synthetic_import import example

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(scope="module")
def database():
    supplied = os.environ.get("TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Set TEST_DATABASE_URL for real PostgreSQL tests")
    admin_url = make_url(supplied)
    assert (admin_url.database or "").startswith("test_")
    name = "test_catalog_read_" + uuid4().hex

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
        session_signing_secret="TEST-CATALOG-" + "x" * 40,
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with pytest.MonkeyPatch.context() as env:
            env.setenv("DATABASE_URL", url)
            env.setenv("APP_ENV", "test")
            command.upgrade(config, "head")
        yield engine, settings
    finally:
        engine.dispose()
        with psycopg.connect(dsn(admin_url), autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def service(database):
    engine, settings = database
    from sqlalchemy import text

    from app.catalog import models as catalog
    from app.ingestion import models

    with engine.begin() as conn:
        tables = list(models.metadata.tables) + list(catalog.metadata.tables)
        conn.execute(text("TRUNCATE " + ",".join(tables)))
    return ImportService(engine, settings, "TEST-REVIEWER", clock=lambda: NOW)


def publish(service, value=None):
    value = value or example()
    offer = next(row for row in value["rows"] if row["kind"] == "offer_snapshots")["data"]
    offer["observed_at"] = NOW.isoformat().replace("+00:00", "Z")
    offer["expires_at"] = (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    batch = ImportInput.model_validate(value)
    job = service.stage(batch)
    review = ReviewInput(
        content_hash=job.content_hash,
        base_version=job.preview.base_version,
        decision="approve",
        note="TEST verified manual record",
    )
    reviewed = service.review(job.id, review)
    return service.publish(
        reviewed.id,
        PublishInput(
            content_hash=reviewed.content_hash, base_version=reviewed.preview.base_version
        ),
    )


def current(service):
    return CatalogReadService(service.engine, service.settings, clock=lambda: NOW)


@pytest.mark.integration
def test_empty_real_namespace_and_published_test_namespace_are_separate(service):
    catalog = current(service)
    assert catalog.list_products()["empty_reason"] == "no_published_catalog"
    result = publish(service)
    listed = catalog.list_products()
    assert listed["data_version"] == result["version_id"] and len(listed["items"]) == 1
    dev = service.settings.model_copy(update={"app_env": "development"})
    assert CatalogReadService(service.engine, dev, clock=lambda: NOW).list_products()["items"] == []


@pytest.mark.integration
def test_detail_keeps_precise_sku_fact_and_public_evidence(service):
    publish(service)
    catalog = current(service)
    product = catalog.list_products()["items"][0]
    detail = catalog.product(product["id"])
    assert detail["manufacturer_part_number"] == "TEST-PN"
    assert detail["facts"][0]["value"] == 8
    evidence = detail["facts"][0]["evidence"]
    assert evidence["source_domain"] == "test.example" and len(evidence["document_hash"]) == 64
    with pytest.raises(DomainError) as error:
        catalog.product(uuid4())
    assert error.value.code == "PRODUCT_NOT_FOUND"


@pytest.mark.integration
def test_list_query_cursor_and_invalid_cursor(service):
    value = example()
    product = next(row for row in value["rows"] if row["kind"] == "product_skus")["data"]
    product["record_key"] = "TEST-Z-SKU"
    publish(service, value)
    catalog = current(service)
    assert catalog.list_products(query="test-pn")["items"][0]["record_key"] == "TEST-Z-SKU"
    assert catalog.list_products(category="gpu")["items"] == []
    with pytest.raises(DomainError) as error:
        catalog.list_products(cursor="bad")
    assert error.value.code == "INVALID_CURSOR"


@pytest.mark.integration
def test_offer_ttl_history_and_eligibility(service):
    publish(service)
    catalog = current(service)
    sku = catalog.list_products()["items"][0]["id"]
    current_offer = catalog.offers(sku, "CN")
    assert len(current_offer["items"]) == 1
    assert current_offer["items"][0]["freshness"] == "current"
    late = CatalogReadService(
        service.engine, service.settings, clock=lambda: NOW + timedelta(days=2)
    )
    assert late.offers(sku, "CN")["items"] == []
    assert late.offers(sku, "CN", include_historical=True)["items"][0]["freshness"] == "historical"


@pytest.mark.integration
def test_price_total_tax_shipping_unknown_and_budget_edges(service):
    publish(service)
    catalog = current(service)
    sku = catalog.list_products()["items"][0]["id"]
    from app.catalog.read_contracts import PriceRequest

    full = PriceService(catalog).quote(
        PriceRequest(region="CN", budget_minor=246912, items=[{"sku_id": sku, "quantity": 2}])
    )
    assert full["total_minor"] == 246912 and full["budget_satisfied"] is True
    one_over = PriceService(catalog).quote(
        PriceRequest(region="CN", budget_minor=246911, items=[{"sku_id": sku, "quantity": 2}])
    )
    assert one_over["budget_satisfied"] is False
    value = example()
    offer = next(row for row in value["rows"] if row["kind"] == "offer_snapshots")["data"]
    offer["id"] = str(uuid4())
    offer["record_key"] = "TEST-UNKNOWN-SHIPPING"
    offer["shipping_minor"] = None
    value["external_batch_id"] = "TEST-UNKNOWN-SHIPPING"
    publish(service, value)
    partial = PriceService(current(service)).quote(
        PriceRequest(
            region="CN", budget_minor=999999, items=[{"sku_id": sku, "offer_id": offer["id"]}]
        )
    )
    assert partial["total_minor"] is None and partial["budget_satisfied"] is None
    assert "SHIPPING_UNKNOWN" in partial["lines"][0]["unpriced_reasons"]


@pytest.mark.integration
def test_wrong_offer_region_and_noncurrent_context_are_rejected(service):
    publish(service)
    catalog = current(service)
    sku = catalog.list_products()["items"][0]["id"]
    offer_id = catalog.offers(sku, "CN")["items"][0]["id"]
    from app.catalog.read_contracts import PriceRequest

    with pytest.raises(DomainError) as error:
        PriceService(catalog).quote(
            PriceRequest(region="US", items=[{"sku_id": sku, "offer_id": offer_id}])
        )
    assert error.value.code == "OFFER_NOT_AVAILABLE"
    with pytest.raises(DomainError) as error:
        PriceService(catalog).quote(PriceRequest(region="CN", items=[{"sku_id": uuid4()}]))
    assert error.value.code == "PRODUCT_NOT_FOUND"


@pytest.mark.integration
def test_public_http_contract_and_empty_frontend_catalog(service):
    with TestClient(create_app(service.settings)) as client:
        empty = client.get("/api/v1/catalog/products").json()
        assert empty["empty_reason"] == "no_published_catalog"
        publish(service)
        response = client.get("/api/v1/catalog/products?category=cpu&region=CN")
        assert response.status_code == 200 and len(response.json()["items"]) == 1
        sku = response.json()["items"][0]["id"]
        assert client.get(f"/api/v1/catalog/products/{sku}").status_code == 200
        quote_body = {"region": "CN", "items": [{"sku_id": sku}]}
        quote = client.post("/api/v1/catalog/price-quotes", json=quote_body)
        assert quote.status_code == 200 and quote.json()["price_complete"] is True
        assert (
            client.post(
                "/api/v1/catalog/price-quotes",
                json={"region": "CN", "items": [{"sku_id": sku, "quantity": 1.0}]},
            ).status_code
            == 422
        )
