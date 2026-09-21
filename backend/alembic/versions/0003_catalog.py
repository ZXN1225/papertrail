"""Frozen T02 DDL. Keep independent of changing application metadata; never seed data."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003_catalog"
down_revision = "0002_sessions"
branch_labels = None
depends_on = None

metadata = sa.MetaData()
CATEGORIES = "'cpu','gpu','motherboard','memory','ssd','psu','case','cooler','laptop'"


def record(name, *columns):
    return sa.Table(
        name,
        metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("record_key", sa.String(120), nullable=False, unique=True),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        *columns,
        sa.UniqueConstraint("id", "synthetic", name=f"uq_{name}_isolation"),
        sa.CheckConstraint(
            "length(btrim(record_key)) > 0 AND record_key = btrim(record_key)",
            name=f"ck_{name}_key",
        ),
        sa.CheckConstraint("synthetic = (record_key LIKE 'TEST-%')", name=f"ck_{name}_synthetic"),
    )


def link(table, column):
    return sa.ForeignKeyConstraint(
        [column, "synthetic"], [f"{table}.id", f"{table}.synthetic"], ondelete="RESTRICT"
    )


def review(name):
    return (
        sa.Column("review_status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("reviewer", sa.String(120)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')", name=f"ck_{name}_review_status"
        ),
        sa.CheckConstraint(
            (
                "(review_status = 'pending' AND reviewer IS NULL AND reviewed_at IS NULL) OR"
                " (review_status <> 'pending' AND reviewer IS NOT NULL AND "
                "length(btrim(reviewer)) > 0 AND reviewed_at IS NOT NULL)"
            ),
            name=f"ck_{name}_review_record",
        ),
    )


brands = record(
    "brands",
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("normalized_name", sa.String(120), nullable=False),
    sa.UniqueConstraint("normalized_name", "synthetic", name="uq_brand_normalized"),
    sa.CheckConstraint(
        (
            "length(btrim(name)) > 0 AND length(normalized_name) > 0 AND normalized_name"
            " = lower(btrim(name))"
        ),
        name="ck_brand_name",
    ),
)

families = record(
    "product_families",
    sa.Column("brand_id", sa.UUID(), nullable=False),
    sa.Column("category", sa.String(16), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    link("brands", "brand_id"),
    sa.UniqueConstraint("id", "synthetic", "brand_id", "category", name="uq_family_identity"),
    sa.CheckConstraint(
        f"category IN ({CATEGORIES}) AND length(btrim(name)) > 0", name="ck_family_category"
    ),
)

skus = record(
    "product_skus",
    sa.Column("family_id", sa.UUID(), nullable=False),
    sa.Column("brand_id", sa.UUID(), nullable=False),
    sa.Column("category", sa.String(16), nullable=False),
    sa.Column("manufacturer_part_number", sa.String(160)),
    sa.Column("normalized_part_number", sa.String(160)),
    sa.Column("region", sa.String(2), nullable=False),
    sa.Column("hardware_revision", sa.String(80)),
    sa.Column("revision_status", sa.String(16), nullable=False, server_default="unknown"),
    sa.Column("configuration_fingerprint", sa.String(64)),
    sa.Column("identity_evidence_id", sa.UUID()),
    sa.Column("identity_status", sa.String(12), nullable=False, server_default="pending"),
    sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
    sa.ForeignKeyConstraint(
        ["family_id", "synthetic", "brand_id", "category"],
        [
            "product_families.id",
            "product_families.synthetic",
            "product_families.brand_id",
            "product_families.category",
        ],
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("id", "synthetic", "category", name="uq_sku_category"),
    sa.UniqueConstraint("id", "synthetic", "region", name="uq_sku_region"),
    sa.ForeignKeyConstraint(
        ["identity_evidence_id", "id", "synthetic"],
        ["evidence_skus.evidence_id", "evidence_skus.sku_id", "evidence_skus.synthetic"],
        name="fk_sku_identity_evidence",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint("region ~ '^[A-Z]{2}$'", name="ck_sku_region"),
    sa.CheckConstraint(
        (
            "status IN ('active','discontinued','unknown') AND identity_status IN "
            "('pending','verified')"
        ),
        name="ck_sku_status",
    ),
    sa.CheckConstraint(
        (
            "(manufacturer_part_number IS NULL AND normalized_part_number IS NULL) OR "
            "(manufacturer_part_number IS NOT NULL AND "
            "length(btrim(manufacturer_part_number)) > 0 AND normalized_part_number IS "
            "NOT NULL AND length(normalized_part_number) > 0 AND normalized_part_number "
            "= lower(btrim(manufacturer_part_number)))"
        ),
        name="ck_sku_part_number",
    ),
    sa.CheckConstraint(
        (
            "(revision_status = 'known' AND hardware_revision IS NOT NULL AND "
            "length(btrim(hardware_revision)) > 0 AND hardware_revision = "
            "lower(btrim(hardware_revision))) OR (revision_status IN "
            "('unknown','not_applicable') AND hardware_revision IS NULL)"
        ),
        name="ck_sku_revision",
    ),
    sa.CheckConstraint(
        "configuration_fingerprint IS NULL OR configuration_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_sku_fingerprint",
    ),
    sa.CheckConstraint(
        (
            "identity_status <> 'verified' OR (identity_evidence_id IS NOT NULL AND "
            "normalized_part_number IS NOT NULL AND revision_status <> 'unknown' AND "
            "(category <> 'laptop' OR configuration_fingerprint IS NOT NULL))"
        ),
        name="ck_sku_verified",
    ),
)
sa.Index(
    "uq_verified_sku_identity",
    skus.c.brand_id,
    skus.c.normalized_part_number,
    skus.c.region,
    skus.c.revision_status,
    skus.c.hardware_revision,
    skus.c.configuration_fingerprint,
    skus.c.synthetic,
    unique=True,
    postgresql_nulls_not_distinct=True,
    postgresql_where=skus.c.identity_status == "verified",
)
sa.Index("ix_sku_catalog", skus.c.category, skus.c.status, skus.c.region)

aliases = record(
    "product_aliases",
    sa.Column("sku_id", sa.UUID(), nullable=False),
    sa.Column("alias", sa.String(200), nullable=False),
    sa.Column("normalized_alias", sa.String(200), nullable=False),
    sa.Column("locale", sa.String(20), nullable=False),
    link("product_skus", "sku_id"),
    sa.UniqueConstraint("sku_id", "normalized_alias", "locale", name="uq_alias_per_sku"),
    sa.CheckConstraint(
        (
            "length(btrim(alias)) > 0 AND normalized_alias = lower(btrim(alias)) AND "
            "length(locale) > 0"
        ),
        name="ck_alias_normalization",
    ),
)
sa.Index("ix_alias_lookup", aliases.c.normalized_alias)

sources = record(
    "sources",
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("domain", sa.String(253), nullable=False),
    sa.Column("source_type", sa.String(16), nullable=False),
    sa.Column("access_method", sa.String(16), nullable=False),
    sa.Column("permission_status", sa.String(16), nullable=False, server_default="unknown"),
    sa.Column("permission_evidence", sa.Text()),
    sa.Column("terms_checked_at", sa.DateTime(timezone=True)),
    sa.Column("allowed_uses", JSONB, nullable=False, server_default="[]"),
    sa.Column("requests_per_minute", sa.Integer()),
    sa.CheckConstraint(
        "length(btrim(name)) > 0 AND domain ~ '^[a-z0-9][a-z0-9.-]*[a-z0-9]$'",
        name="ck_source_identity",
    ),
    sa.CheckConstraint(
        (
            "source_type IN ('manufacturer','merchant','benchmark','manual') AND "
            "access_method IN ('manual','api','web','file')"
        ),
        name="ck_source_type",
    ),
    sa.CheckConstraint(
        (
            "permission_status IN ('unknown','allowed','restricted','denied') AND "
            "jsonb_typeof(allowed_uses) = 'array'"
        ),
        name="ck_source_permission",
    ),
    sa.CheckConstraint(
        (
            "(permission_status IN ('unknown','denied') AND allowed_uses = '[]'::jsonb) "
            "OR (permission_status IN ('allowed','restricted') AND permission_evidence "
            "IS NOT NULL AND length(btrim(permission_evidence)) > 0 AND terms_checked_at"
            " IS NOT NULL AND jsonb_array_length(allowed_uses) > 0)"
        ),
        name="ck_source_permission_evidence",
    ),
    sa.CheckConstraint(
        (
            "allowed_uses <@ "
            '\'["internal_review","public_display","automated_fetch","excerpt_storage"]\'::jsonb'
        ),
        name="ck_source_uses",
    ),
    sa.CheckConstraint(
        "requests_per_minute IS NULL OR requests_per_minute > 0", name="ck_source_rate"
    ),
)

documents = record(
    "source_documents",
    sa.Column("source_id", sa.UUID(), nullable=False),
    sa.Column("canonical_url", sa.Text(), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("parser_version", sa.String(80), nullable=False),
    sa.Column("storage_key", sa.String(300)),
    link("sources", "source_id"),
    sa.CheckConstraint(
        "canonical_url ~ '^https?://[^/@[:space:]]+(/|$)' AND canonical_url !~ '[#[:space:]]'",
        name="ck_document_url",
    ),
    sa.CheckConstraint(
        (
            "content_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(title)) > 0 AND "
            "length(btrim(parser_version)) > 0"
        ),
        name="ck_document_hash",
    ),
    sa.CheckConstraint(
        "published_at IS NULL OR published_at <= fetched_at", name="ck_document_time"
    ),
    sa.CheckConstraint(
        (
            "storage_key IS NULL OR (storage_key ~ '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$'"
            " AND storage_key !~ '(^|/)\\.\\.?(/|$)')"
        ),
        name="ck_document_storage",
    ),
)
sa.Index("ix_document_source", documents.c.source_id, documents.c.fetched_at)

evidence = record(
    "evidence",
    sa.Column("document_id", sa.UUID(), nullable=False),
    sa.Column("locator_kind", sa.String(16), nullable=False),
    sa.Column("locator", sa.String(500), nullable=False),
    sa.Column("excerpt_sha256", sa.String(64), nullable=False),
    *review("evidence"),
    link("source_documents", "document_id"),
    sa.CheckConstraint(
        (
            "locator_kind IN ('page','section','selector','json_pointer') AND "
            "length(btrim(locator)) > 0 AND excerpt_sha256 ~ '^[0-9a-f]{64}$'"
        ),
        name="ck_evidence_locator",
    ),
)
sa.Index("ix_evidence_document", evidence.c.document_id)

evidence_skus = sa.Table(
    "evidence_skus",
    metadata,
    sa.Column("evidence_id", sa.UUID(), primary_key=True),
    sa.Column("sku_id", sa.UUID(), primary_key=True),
    sa.Column("synthetic", sa.Boolean(), nullable=False),
    sa.UniqueConstraint("evidence_id", "sku_id", "synthetic", name="uq_evidence_sku_scope"),
    link("evidence", "evidence_id"),
    link("product_skus", "sku_id"),
)

attributes = record(
    "attribute_definitions",
    sa.Column("key", sa.String(80), nullable=False),
    sa.Column("category", sa.String(16), nullable=False),
    sa.Column("value_type", sa.String(12), nullable=False),
    sa.Column("canonical_unit", sa.String(24), nullable=False),
    sa.Column("description", sa.String(300), nullable=False),
    sa.UniqueConstraint("category", "key", "synthetic", name="uq_attribute_key"),
    sa.UniqueConstraint(
        "id", "synthetic", "category", "value_type", "canonical_unit", name="uq_attribute_type_unit"
    ),
    sa.CheckConstraint(
        f"category IN ({CATEGORIES}) AND key ~ '^[a-z][a-z0-9_]*$'", name="ck_attribute_key"
    ),
    sa.CheckConstraint(
        (
            "value_type IN ('text','integer','decimal','boolean') AND "
            "length(btrim(canonical_unit)) > 0 AND length(btrim(description)) > 0"
        ),
        name="ck_attribute_definition",
    ),
)

facts = record(
    "spec_facts",
    sa.Column("sku_id", sa.UUID(), nullable=False),
    sa.Column("attribute_id", sa.UUID(), nullable=False),
    sa.Column("evidence_id", sa.UUID(), nullable=False),
    sa.Column("category", sa.String(16), nullable=False),
    sa.Column("value_type", sa.String(12), nullable=False),
    sa.Column("unit", sa.String(24), nullable=False),
    sa.Column("value_text", sa.String(1000)),
    sa.Column("value_integer", sa.BigInteger()),
    sa.Column("value_decimal", sa.Numeric(28, 8)),
    sa.Column("value_boolean", sa.Boolean()),
    sa.Column("missing_reason", sa.String(20)),
    sa.Column("raw_value", sa.String(1000)),
    sa.Column("raw_unit", sa.String(80)),
    sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_to", sa.DateTime(timezone=True)),
    *review("fact"),
    sa.ForeignKeyConstraint(
        ["sku_id", "synthetic", "category"],
        ["product_skus.id", "product_skus.synthetic", "product_skus.category"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["attribute_id", "synthetic", "category", "value_type", "unit"],
        [
            "attribute_definitions.id",
            "attribute_definitions.synthetic",
            "attribute_definitions.category",
            "attribute_definitions.value_type",
            "attribute_definitions.canonical_unit",
        ],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["evidence_id", "sku_id", "synthetic"],
        ["evidence_skus.evidence_id", "evidence_skus.sku_id", "evidence_skus.synthetic"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        (
            "(missing_reason IS NOT NULL AND missing_reason IN "
            "('not_collected','not_disclosed','conflicting','not_applicable') AND "
            "num_nonnulls(value_text,value_integer,value_decimal,value_boolean) = 0) OR "
            "(missing_reason IS NULL AND "
            "num_nonnulls(value_text,value_integer,value_decimal,value_boolean) = 1 AND "
            "raw_value IS NOT NULL AND length(btrim(raw_value)) > 0 AND ((value_type = "
            "'text' AND value_text IS NOT NULL AND length(btrim(value_text)) > 0) OR "
            "(value_type = 'integer' AND value_integer IS NOT NULL) OR (value_type = "
            "'decimal' AND value_decimal IS NOT NULL AND value_decimal NOT IN "
            "('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)) OR (value_type ="
            " 'boolean' AND value_boolean IS NOT NULL)))"
        ),
        name="ck_fact_typed_value",
    ),
    sa.CheckConstraint(
        (
            "missing_reason IS NULL OR missing_reason IN "
            "('not_collected','not_disclosed','conflicting','not_applicable')"
        ),
        name="ck_fact_missing",
    ),
    sa.CheckConstraint(
        "jsonb_typeof(conditions) = 'object' AND (valid_to IS NULL OR valid_to > valid_from)",
        name="ck_fact_time_conditions",
    ),
)
sa.Index("ix_fact_sku_attribute", facts.c.sku_id, facts.c.attribute_id)

merchants = record(
    "merchants",
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("platform", sa.String(100), nullable=False),
    sa.Column("external_seller_id", sa.String(160), nullable=False),
    sa.UniqueConstraint("platform", "external_seller_id", "synthetic", name="uq_merchant_external"),
    sa.CheckConstraint(
        (
            "length(btrim(name)) > 0 AND length(btrim(platform)) > 0 AND "
            "length(btrim(external_seller_id)) > 0"
        ),
        name="ck_merchant_identity",
    ),
)

listings = record(
    "merchant_listings",
    sa.Column("merchant_id", sa.UUID(), nullable=False),
    sa.Column("source_id", sa.UUID(), nullable=False),
    sa.Column("external_listing_id", sa.String(160), nullable=False),
    sa.Column("listing_url", sa.Text(), nullable=False),
    sa.Column("matched_sku_id", sa.UUID()),
    sa.Column("match_evidence_id", sa.UUID()),
    sa.Column("match_status", sa.String(12), nullable=False, server_default="pending"),
    link("merchants", "merchant_id"),
    link("sources", "source_id"),
    sa.UniqueConstraint(
        "merchant_id", "external_listing_id", "synthetic", name="uq_listing_external"
    ),
    sa.UniqueConstraint("id", "synthetic", "matched_sku_id", name="uq_listing_matched_sku"),
    sa.ForeignKeyConstraint(
        ["match_evidence_id", "matched_sku_id", "synthetic"],
        ["evidence_skus.evidence_id", "evidence_skus.sku_id", "evidence_skus.synthetic"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        (
            "(match_status = 'matched' AND matched_sku_id IS NOT NULL AND "
            "match_evidence_id IS NOT NULL) OR (match_status IN "
            "('pending','ambiguous','rejected') AND matched_sku_id IS NULL AND "
            "match_evidence_id IS NULL)"
        ),
        name="ck_listing_match",
    ),
    sa.CheckConstraint(
        (
            "length(btrim(external_listing_id)) > 0 AND listing_url ~ "
            "'^https?://[^/@[:space:]]+(/|$)' AND listing_url !~ '[#[:space:]]'"
        ),
        name="ck_listing_url",
    ),
)

offers = record(
    "offer_snapshots",
    sa.Column("listing_id", sa.UUID(), nullable=False),
    sa.Column("sku_id", sa.UUID(), nullable=False),
    sa.Column("evidence_id", sa.UUID(), nullable=False),
    sa.Column("amount_minor", sa.BigInteger()),
    sa.Column("amount_missing_reason", sa.String(20)),
    sa.Column("shipping_minor", sa.BigInteger()),
    sa.Column("tax_minor", sa.BigInteger()),
    sa.Column("tax_included", sa.Boolean()),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("region", sa.String(2), nullable=False),
    sa.Column("stock_status", sa.String(16), nullable=False, server_default="unknown"),
    sa.Column("condition", sa.String(16), nullable=False, server_default="unknown"),
    sa.Column("eligibility_type", sa.String(16), nullable=False, server_default="unknown"),
    sa.Column("eligibility_details", sa.String(1000)),
    sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    *review("offer"),
    sa.ForeignKeyConstraint(
        ["listing_id", "synthetic", "sku_id"],
        ["merchant_listings.id", "merchant_listings.synthetic", "merchant_listings.matched_sku_id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["evidence_id", "sku_id", "synthetic"],
        ["evidence_skus.evidence_id", "evidence_skus.sku_id", "evidence_skus.synthetic"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["sku_id", "synthetic", "region"],
        ["product_skus.id", "product_skus.synthetic", "product_skus.region"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        (
            "(amount_minor IS NULL AND amount_missing_reason IS NOT NULL AND "
            "amount_missing_reason IN "
            "('not_collected','not_disclosed','conflicting','not_applicable')) OR "
            "(amount_minor IS NOT NULL AND amount_minor >= 0 AND amount_missing_reason "
            "IS NULL)"
        ),
        name="ck_offer_amount",
    ),
    sa.CheckConstraint(
        (
            "(shipping_minor IS NULL OR shipping_minor >= 0) AND (tax_minor IS NULL OR "
            "tax_minor >= 0) AND (tax_included IS DISTINCT FROM TRUE OR tax_minor IS "
            "NULL OR tax_minor = 0)"
        ),
        name="ck_offer_fees",
    ),
    sa.CheckConstraint(
        "currency ~ '^[A-Z]{3}$' AND region ~ '^[A-Z]{2}$' AND expires_at > observed_at",
        name="ck_offer_currency_time",
    ),
    sa.CheckConstraint(
        (
            "stock_status IN ('in_stock','out_of_stock','preorder','unknown') AND "
            "condition IN ('new','used','refurbished','unknown')"
        ),
        name="ck_offer_availability",
    ),
    sa.CheckConstraint(
        (
            "eligibility_type IN ('unconditional','member','coupon','bundle','unknown') "
            "AND (eligibility_type IN ('unconditional','unknown') OR "
            "(eligibility_details IS NOT NULL AND length(btrim(eligibility_details)) > "
            "0))"
        ),
        name="ck_offer_eligibility",
    ),
)
sa.Index("ix_offer_listing_observed", offers.c.listing_id, offers.c.observed_at.desc())


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=False)
