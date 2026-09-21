"""TEST-T02 synthetic records; all persistence is confined to a disposable test_* database."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.catalog import contracts as c
from app.catalog import models as m
from app.common.config import Settings
from app.main import create_app
from app.profiles.contracts import ProfileInput
from app.profiles.service import ProfileService

NOW = datetime(2026, 9, 21, tzinfo=UTC)
CASE_METADATA = {"case_id": "TEST-T02", "synthetic": True}


def record(**values):
    return {"id": uuid4(), "record_key": "TEST-" + uuid4().hex, "synthetic": True, **values}


def offer_input(**values):
    return record(
        listing_id=uuid4(),
        sku_id=uuid4(),
        evidence_id=uuid4(),
        amount_minor=600001,
        currency="CNY",
        region="CN",
        observed_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        **values,
    )


@pytest.mark.parametrize("value", [-1, True, False, 1.2, "100", 9223372036854775808])
def test_money_rejects_non_integer_or_out_of_range(value):
    data = offer_input()
    data["amount_minor"] = value
    with pytest.raises(ValidationError):
        c.CatalogOffer.model_validate(data)


@pytest.mark.parametrize(
    "change",
    [
        {"amount_minor": None},
        {"amount_missing_reason": "not_collected"},
        {"shipping_minor": -1},
        {"tax_included": True, "tax_minor": 1},
        {"expires_at": NOW},
        {"observed_at": NOW.replace(tzinfo=None)},
        {"eligibility_type": "coupon"},
        {"owner_id": "untrusted"},
        {"synthetic": False},
        {"record_key": "UNMARKED"},
    ],
)
def test_offer_contract_rejects_incomplete_or_unsafe_records(change):
    with pytest.raises(ValidationError):
        c.CatalogOffer.model_validate({**offer_input(), **change})


def test_unknown_price_is_not_zero():
    data = {**offer_input(), "amount_minor": None, "amount_missing_reason": "not_collected"}
    result = c.CatalogOffer.model_validate(data)
    assert result.amount_minor is None and result.shipping_minor is None
    assert result.tax_included is None and result.stock_status == "unknown"
    assert c.CatalogOffer.model_validate(offer_input()).amount_minor == 600001


def fact_input(**values):
    return (
        record(
            sku_id=uuid4(),
            attribute_id=uuid4(),
            evidence_id=uuid4(),
            category="cpu",
            value_type="integer",
            unit="count",
            value_integer=8,
            raw_value="8",
            valid_from=NOW,
        )
        | values
    )


@pytest.mark.parametrize(
    "change",
    [
        {"value_integer": None},
        {"value_integer": True},
        {"value_text": "8"},
        {"missing_reason": "not_collected"},
        {"unit": ""},
        {"raw_value": None},
        {"value_type": "decimal", "value_integer": None, "value_decimal": 1.2},
        {"value_type": "decimal", "value_integer": None, "value_decimal": "NaN"},
        {"value_type": "decimal", "value_integer": None, "value_decimal": "0.123456789"},
        {"valid_to": NOW - timedelta(seconds=1)},
        {"review_status": "approved"},
    ],
)
def test_fact_contract_rejects_wrong_types_and_untraceable_claims(change):
    with pytest.raises(ValidationError):
        c.CatalogFact.model_validate(fact_input(**change))


def test_missing_and_decimal_facts_preserve_semantics():
    missing = c.CatalogFact.model_validate(
        fact_input(value_integer=None, missing_reason="not_disclosed", raw_value=None)
    )
    assert missing.value_integer is None
    precise = c.CatalogFact.model_validate(
        fact_input(value_integer=None, value_type="decimal", value_decimal="0.12345678")
    )
    assert precise.value_decimal == Decimal("0.12345678")


def test_source_permissions_never_default_to_allowed():
    values = record(
        name="TEST-SOURCE", domain="source.example", source_type="manual", access_method="manual"
    )
    source = c.CatalogSource.model_validate(values)
    assert source.permission_status == "unknown" and source.allowed_uses == []
    for changes in ({"permission_status": "allowed"}, {"allowed_uses": ["public_display"]}):
        with pytest.raises(ValidationError):
            c.CatalogSource.model_validate(values | changes)


@pytest.mark.parametrize(
    "url",
    [
        "file:///private",
        "http://user:pass@example.com/a",
        "https://example.com/a#section",
        "http://",
    ],
)
def test_document_url_is_metadata_not_an_arbitrary_fetch_tool(url):
    with pytest.raises(ValidationError):
        c.CatalogDocument.model_validate(
            record(
                source_id=uuid4(),
                title="TEST-DOC",
                canonical_url=url,
                content_sha256="a" * 64,
                fetched_at=NOW,
                parser_version="TEST-1",
            )
        )


@pytest.fixture(scope="module")
def database():
    supplied = os.environ.get("TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("Set TEST_DATABASE_URL for real PostgreSQL tests")
    admin_url = make_url(supplied)
    assert (admin_url.database or "").startswith("test_")
    name = "test_t02_" + uuid4().hex

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
        session_signing_secret="TEST-SESSION-SECRET-" + "x" * 32,
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with pytest.MonkeyPatch.context() as env:
            env.setenv("DATABASE_URL", url)
            env.setenv("APP_ENV", "test")
            command.upgrade(config, "0002_sessions")
            service = ProfileService(engine, settings)
            _, cookie = service.bootstrap(None)
            profile = service.save(
                cookie,
                ProfileInput(
                    mode="pc",
                    budget_max_minor=600001,
                    budget_scope=["tower"],
                    workloads=["office"],
                    excluded_brands=["TEST-BRAND"],
                ),
            )
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            assert service.current(cookie)["profile"] == profile
            command.downgrade(config, "0002_sessions")
            assert not set(m.metadata.tables) & set(inspect(engine).get_table_names())
            assert service.current(cookie)["profile"] == profile
            command.upgrade(config, "head")
            assert service.current(cookie)["profile"] == profile
        yield engine, settings
    finally:
        engine.dispose()
        with psycopg.connect(dsn(admin_url), autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def conn(database):
    with database[0].connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


def put(conn, table, model, **fields):
    data = model.model_validate(record(**fields)).model_dump()
    conn.execute(table.insert().values(**data))
    return data


@pytest.fixture
def graph(conn):
    brand = put(conn, m.brands, c.CatalogBrand, name="TEST-BRAND", normalized_name="test-brand")
    family = put(
        conn, m.families, c.CatalogFamily, brand_id=brand["id"], category="cpu", name="TEST-FAMILY"
    )
    sku = put(
        conn,
        m.skus,
        c.CatalogSKU,
        family_id=family["id"],
        brand_id=brand["id"],
        category="cpu",
        manufacturer_part_number="TEST-PN",
        normalized_part_number="test-pn",
        region="CN",
        revision_status="not_applicable",
    )
    source = put(
        conn,
        m.sources,
        c.CatalogSource,
        name="TEST-SOURCE",
        domain="source.example",
        source_type="manual",
        access_method="manual",
    )
    document = put(
        conn,
        m.documents,
        c.CatalogDocument,
        source_id=source["id"],
        canonical_url="https://source.example/test",
        title="TEST-DOC",
        content_sha256="a" * 64,
        fetched_at=NOW,
        parser_version="TEST-1",
    )
    evidence = put(
        conn,
        m.evidence,
        c.CatalogEvidence,
        document_id=document["id"],
        locator_kind="section",
        locator="TEST-SECTION",
        excerpt_sha256="b" * 64,
    )
    conn.execute(
        m.evidence_skus.insert().values(
            evidence_id=evidence["id"], sku_id=sku["id"], synthetic=True
        )
    )
    sku.update(identity_evidence_id=evidence["id"], identity_status="verified")
    conn.execute(
        update(m.skus)
        .where(m.skus.c.id == sku["id"])
        .values(identity_status="verified", identity_evidence_id=evidence["id"])
    )
    attribute = put(
        conn,
        m.attributes,
        c.CatalogAttribute,
        key="test_count",
        category="cpu",
        value_type="integer",
        canonical_unit="count",
        description="TEST-count, not a real product specification",
    )
    fact = put(
        conn,
        m.facts,
        c.CatalogFact,
        sku_id=sku["id"],
        evidence_id=evidence["id"],
        attribute_id=attribute["id"],
        category="cpu",
        value_type="integer",
        unit="count",
        value_integer=8,
        raw_value="8",
        valid_from=NOW,
    )
    merchant = put(
        conn,
        m.merchants,
        c.CatalogMerchant,
        name="TEST-MERCHANT",
        platform="TEST-PLATFORM",
        external_seller_id="TEST-SELLER",
    )
    listing = put(
        conn,
        m.listings,
        c.CatalogListing,
        merchant_id=merchant["id"],
        source_id=source["id"],
        external_listing_id="TEST-LISTING",
        listing_url="https://source.example/test-listing",
        matched_sku_id=sku["id"],
        match_evidence_id=evidence["id"],
        match_status="matched",
    )
    offer = put(
        conn,
        m.offers,
        c.CatalogOffer,
        listing_id=listing["id"],
        sku_id=sku["id"],
        evidence_id=evidence["id"],
        amount_minor=600001,
        currency="CNY",
        region="CN",
        observed_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    return {
        "brands": brand,
        "product_families": family,
        "product_skus": sku,
        "sources": source,
        "source_documents": document,
        "evidence": evidence,
        "attribute_definitions": attribute,
        "spec_facts": fact,
        "merchants": merchant,
        "merchant_listings": listing,
        "offer_snapshots": offer,
    }


@pytest.mark.integration
def test_migration_preserves_sessions_and_empty_catalog(database):
    engine, settings = database
    assert set(m.metadata.tables) <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        for table in m.metadata.tables.values():
            assert conn.scalar(select(func.count()).select_from(table)) == 0
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
        assert client.get("/api/v1/platform/status").json()["recommendation_available"] is False
        assert client.get("/api/v1/catalog/products").status_code == 404


@pytest.mark.integration
def test_complete_chain_and_conflicts_are_preserved(conn, graph):
    offer = conn.execute(select(m.offers)).mappings().one()
    assert offer["amount_minor"] == 600001 and offer["shipping_minor"] is None
    joined = conn.execute(
        select(m.sources.c.domain).select_from(
            m.offers.join(m.evidence, m.offers.c.evidence_id == m.evidence.c.id)
            .join(m.documents, m.evidence.c.document_id == m.documents.c.id)
            .join(m.sources, m.documents.c.source_id == m.sources.c.id)
        )
    ).scalar_one()
    assert joined == "source.example"
    original = graph["spec_facts"]
    alternate = {
        **original,
        "id": uuid4(),
        "record_key": "TEST-ALTERNATE",
        "value_integer": 12,
        "raw_value": "12",
    }
    conn.execute(m.facts.insert().values(**alternate))
    assert conn.scalar(select(func.count()).select_from(m.facts)) == 2
    assert conn.scalar(select(m.facts.c.value_integer).where(m.facts.c.id == original["id"])) == 8


@pytest.mark.integration
@pytest.mark.parametrize(
    "table_name,change",
    [
        ("brands", {"normalized_name": "NOT-NORMALIZED"}),
        ("sources", {"permission_status": "allowed"}),
        ("sources", {"allowed_uses": ["public_display"]}),
        ("source_documents", {"source_id": uuid4()}),
        ("source_documents", {"canonical_url": "https://user:pass@source.example/test"}),
        ("source_documents", {"published_at": NOW + timedelta(days=1)}),
        ("evidence", {"review_status": "approved"}),
        ("product_skus", {"identity_evidence_id": None}),
        ("spec_facts", {"value_integer": None}),
        ("spec_facts", {"value_text": "8"}),
        ("spec_facts", {"missing_reason": "not_disclosed"}),
        ("spec_facts", {"unit": "MHz"}),
        ("spec_facts", {"category": "memory"}),
        ("spec_facts", {"valid_to": NOW}),
        ("spec_facts", {"conditions": []}),
        ("offer_snapshots", {"amount_minor": -1}),
        ("offer_snapshots", {"amount_minor": None}),
        ("offer_snapshots", {"shipping_minor": -1}),
        ("offer_snapshots", {"tax_included": True, "tax_minor": 1}),
        ("offer_snapshots", {"expires_at": NOW}),
        ("offer_snapshots", {"region": "US"}),
        ("offer_snapshots", {"eligibility_type": "member"}),
        ("offer_snapshots", {"synthetic": False, "record_key": "FORGED-REAL"}),
    ],
)
def test_database_rejects_invalid_rows_without_pydantic(conn, graph, table_name, change):
    table = m.metadata.tables[table_name]
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                update(table).where(table.c.id == graph[table_name]["id"]).values(**change)
            )
            conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.integration
def test_verified_identity_unique_with_null_revision_and_fingerprint(conn, graph):
    # The identity scope FK is deferred so the UNIQUE key is tested independently.
    conn.execute(text("SET CONSTRAINTS fk_sku_identity_evidence DEFERRED"))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(
                m.skus.insert().values(
                    **{**graph["product_skus"], "id": uuid4(), "record_key": "TEST-DUPLICATE"}
                )
            )
    assert error.value.orig.sqlstate == "23505"


@pytest.mark.integration
def test_pending_identities_do_not_merge_and_aliases_can_be_ambiguous(conn, graph):
    sku = {
        **graph["product_skus"],
        "id": uuid4(),
        "record_key": "TEST-PENDING",
        "identity_status": "pending",
        "identity_evidence_id": None,
        "manufacturer_part_number": None,
        "normalized_part_number": None,
        "revision_status": "unknown",
    }
    conn.execute(m.skus.insert().values(**sku))
    for target in [sku["id"], graph["product_skus"]["id"]]:
        put(
            conn,
            m.aliases,
            c.CatalogAlias,
            sku_id=target,
            alias="TEST-AMBIGUOUS",
            normalized_alias="test-ambiguous",
            locale="zh-CN",
        )
    assert conn.scalar(select(func.count()).select_from(m.aliases)) == 2
    # A valid evidence record for another SKU cannot substantiate this SKU's facts/quote.
    other = put(
        conn,
        m.evidence,
        c.CatalogEvidence,
        document_id=graph["source_documents"]["id"],
        locator_kind="section",
        locator="TEST-OTHER",
        excerpt_sha256="c" * 64,
    )
    conn.execute(
        m.evidence_skus.insert().values(evidence_id=other["id"], sku_id=sku["id"], synthetic=True)
    )
    for table in [m.facts, m.offers]:
        with pytest.raises(IntegrityError) as error:
            with conn.begin_nested():
                conn.execute(update(table).values(evidence_id=other["id"]))
        assert error.value.orig.sqlstate == "23503"


@pytest.mark.integration
def test_missing_values_and_unmatched_listing(conn, graph):
    conn.execute(update(m.offers).values(amount_minor=None, amount_missing_reason="not_collected"))
    conn.execute(
        update(m.facts).values(value_integer=None, raw_value=None, missing_reason="not_disclosed")
    )
    assert conn.scalar(select(m.offers.c.amount_minor)) is None
    pending = put(
        conn,
        m.listings,
        c.CatalogListing,
        merchant_id=graph["merchants"]["id"],
        source_id=graph["sources"]["id"],
        external_listing_id="TEST-PENDING",
        listing_url="https://source.example/pending",
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(update(m.offers).values(listing_id=pending["id"]))


def test_openapi_documents_records_without_exposing_import_routes():
    schema = create_app(
        Settings(_env_file=None, app_env="test", database_url="", redis_url="")
    ).openapi()
    assert "CatalogOffer" in schema["components"]["schemas"]
    assert "CatalogSKU" in schema["components"]["schemas"]
    assert not any("imports" in path or "catalog" in path for path in schema["paths"])


@pytest.mark.integration
def test_regions_and_laptop_configurations_remain_distinct(conn, graph):
    family = put(
        conn,
        m.families,
        c.CatalogFamily,
        brand_id=graph["brands"]["id"],
        category="laptop",
        name="TEST-LAPTOP",
    )
    created = []
    for region, fingerprint in [("CN", "a" * 64), ("CN", "b" * 64), ("US", "a" * 64)]:
        sku = put(
            conn,
            m.skus,
            c.CatalogSKU,
            family_id=family["id"],
            brand_id=graph["brands"]["id"],
            category="laptop",
            region=region,
            manufacturer_part_number="TEST-LAPTOP-PN",
            normalized_part_number="test-laptop-pn",
            revision_status="not_applicable",
            configuration_fingerprint=fingerprint,
        )
        conn.execute(
            m.evidence_skus.insert().values(
                evidence_id=graph["evidence"]["id"],
                sku_id=sku["id"],
                synthetic=True,
            )
        )
        conn.execute(
            update(m.skus)
            .where(m.skus.c.id == sku["id"])
            .values(
                identity_status="verified",
                identity_evidence_id=graph["evidence"]["id"],
            )
        )
        created.append(sku["id"])
    assert (
        conn.scalar(select(func.count()).select_from(m.skus).where(m.skus.c.id.in_(created))) == 3
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                update(m.skus)
                .where(m.skus.c.id == created[0])
                .values(
                    configuration_fingerprint=None,
                )
            )
