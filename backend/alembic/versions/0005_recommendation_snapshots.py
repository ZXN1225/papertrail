"""Immutable saved recommendation results and idempotency records."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_recommendation_snapshots"
down_revision = "0004_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendation_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("lineage_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("recommendation_snapshots.id")),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.UUID(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("data_version", sa.UUID()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lineage_id", "revision", name="uq_recommendation_lineage_revision"),
        sa.CheckConstraint("revision > 0", name="ck_recommendation_revision_positive"),
        sa.CheckConstraint("mode IN ('laptop', 'pc')", name="ck_recommendation_mode"),
    )
    op.create_index(
        "ix_recommendation_snapshots_lineage", "recommendation_snapshots", ["lineage_id"]
    )
    op.create_table(
        "recommendation_idempotency",
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("path", sa.String(160), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.UUID(),
            sa.ForeignKey("recommendation_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("recommendation_idempotency")
    op.drop_index("ix_recommendation_snapshots_lineage", table_name="recommendation_snapshots")
    op.drop_table("recommendation_snapshots")
