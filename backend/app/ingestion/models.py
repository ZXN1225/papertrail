"""Publication metadata; catalog rows are immutable through the ingestion service."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
jobs = sa.Table(
    "ingestion_jobs",
    metadata,
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column("source_id", sa.UUID(), nullable=False),
    sa.Column("external_batch_id", sa.String(120), nullable=False),
    sa.Column("synthetic", sa.Boolean(), nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("raw_snapshot", JSONB, nullable=False),
    sa.Column("preview", JSONB, nullable=False),
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("checkpoint", sa.String(12), nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("reviewer", sa.String(120)),
    sa.Column("review_note", sa.String(1000)),
    sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    sa.Column("selected_fact_ids", JSONB, nullable=False, server_default="[]"),
    sa.Column(
        "version_id",
        sa.UUID(),
        sa.ForeignKey("dataset_versions.id", name="fk_job_version", use_alter=True),
    ),
    sa.UniqueConstraint("id", "synthetic", name="uq_job_namespace"),
    sa.UniqueConstraint("source_id", "external_batch_id", "synthetic", name="uq_ingestion_batch"),
    sa.CheckConstraint("status IN ('invalid','staged','approved','rejected','published')"),
    sa.CheckConstraint("checkpoint IN ('validated','reviewed','published')"),
    sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'"),
    sa.CheckConstraint(
        "status NOT IN ('approved','rejected','published') OR "
        "(reviewer IS NOT NULL AND review_note IS NOT NULL AND reviewed_at IS NOT NULL)"
    ),
    sa.CheckConstraint("(status = 'published') = (version_id IS NOT NULL)"),
)
versions = sa.Table(
    "dataset_versions",
    metadata,
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column("job_id", sa.UUID(), sa.ForeignKey("ingestion_jobs.id"), nullable=False, unique=True),
    sa.Column("parent_id", sa.UUID()),
    sa.Column("synthetic", sa.Boolean(), nullable=False),
    sa.Column("records", JSONB, nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("published_by", sa.String(120), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("id", "synthetic", name="uq_dataset_namespace"),
    sa.ForeignKeyConstraint(
        ["parent_id", "synthetic"], ["dataset_versions.id", "dataset_versions.synthetic"]
    ),
    sa.ForeignKeyConstraint(
        ["job_id", "synthetic"], ["ingestion_jobs.id", "ingestion_jobs.synthetic"]
    ),
)
pointers = sa.Table(
    "dataset_pointers",
    metadata,
    sa.Column("synthetic", sa.Boolean(), primary_key=True),
    sa.Column("version_id", sa.UUID()),
    sa.ForeignKeyConstraint(
        ["version_id", "synthetic"], ["dataset_versions.id", "dataset_versions.synthetic"]
    ),
)
canonical = sa.Table(
    "canonical_specs",
    metadata,
    sa.Column("version_id", sa.UUID(), sa.ForeignKey("dataset_versions.id"), primary_key=True),
    sa.Column("sku_id", sa.UUID(), primary_key=True),
    sa.Column("attribute_id", sa.UUID(), primary_key=True),
    sa.Column("conditions_hash", sa.String(64), primary_key=True),
    sa.Column("fact_id", sa.UUID(), nullable=False),
    sa.Column("synthetic", sa.Boolean(), nullable=False),
    sa.Column("value_type", sa.String(12), nullable=False),
    sa.Column("unit", sa.String(24), nullable=False),
    sa.Column("value_text", sa.String(1000)),
    sa.Column("value_integer", sa.BigInteger()),
    sa.Column("value_decimal", sa.Numeric(28, 8)),
    sa.Column("value_boolean", sa.Boolean()),
    sa.Column("missing_reason", sa.String(20)),
    sa.Column("conditions", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["version_id", "synthetic"], ["dataset_versions.id", "dataset_versions.synthetic"]
    ),
)
sa.Index(
    "ix_canonical_filter",
    canonical.c.version_id,
    canonical.c.attribute_id,
    canonical.c.value_integer,
    canonical.c.value_decimal,
)
outbox = sa.Table(
    "publication_outbox",
    metadata,
    sa.Column("id", sa.UUID(), primary_key=True),
    sa.Column(
        "version_id", sa.UUID(), sa.ForeignKey("dataset_versions.id"), nullable=False, unique=True
    ),
    sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("lease_id", sa.UUID()),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("last_error", sa.String(80)),
    sa.CheckConstraint("status IN ('pending','leased','delivered') AND attempts >= 0"),
)
sa.Index("ix_outbox_due", outbox.c.status, outbox.c.next_run_at)
notifications = sa.Table(
    "dataset_notifications",
    metadata,
    sa.Column("version_id", sa.UUID(), sa.ForeignKey("dataset_versions.id"), primary_key=True),
    sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
)

# Fixed cross-module DDL; the frozen migration contains its own copy.
for statement in (
    "ALTER TABLE spec_facts ADD CONSTRAINT uq_fact_projection_ref "
    "UNIQUE (id,sku_id,attribute_id,synthetic)",
    "ALTER TABLE canonical_specs ADD CONSTRAINT fk_canonical_fact "
    "FOREIGN KEY (fact_id,sku_id,attribute_id,synthetic) "
    "REFERENCES spec_facts (id,sku_id,attribute_id,synthetic)",
):
    sa.event.listen(metadata, "after_create", sa.DDL(statement))
sa.event.listen(
    metadata, "after_drop", sa.DDL("ALTER TABLE spec_facts DROP CONSTRAINT uq_fact_projection_ref")
)
