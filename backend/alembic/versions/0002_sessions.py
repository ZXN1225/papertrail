"""Anonymous identities and immutable profile snapshots; no product data."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_sessions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anonymous_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_anonymous_sessions_expires_at", "anonymous_sessions", ["expires_at"])
    op.create_table(
        "profiles",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_profile_revision_positive"),
    )
    op.create_table(
        "profile_revisions",
        sa.Column(
            "profile_id",
            sa.UUID(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("origins", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_snapshot_revision_positive"),
    )
    op.create_table(
        "request_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("request_limits")
    op.drop_table("profile_revisions")
    op.drop_table("profiles")
    op.drop_table("anonymous_sessions")
