"""Reviewed knowledge documents and keyword-search chunks."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_knowledge_bm25"
down_revision = "0005_recommendation_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("data_version", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.String(2000), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("region", sa.String(2)),
        sa.Column("sku_ids", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("review_status", sa.String(12), nullable=False),
        sa.Column("reviewer", sa.String(120)),
        sa.Column("review_note", sa.String(1000)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("review_status IN ('pending','approved','rejected')"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "ordinal"),
    )


def downgrade():
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
