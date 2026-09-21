"""Persist bounded agent conversations, runs, and replayable events."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_agent_runs"
down_revision = "0006_knowledge_bm25"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_sessions_session_id", "agent_sessions", ["session_id"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "agent_session_id",
            sa.UUID(),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.UUID(),
            sa.ForeignKey("profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("answer", postgresql.JSONB()),
        sa.Column("pending_question", sa.String(500)),
        sa.Column("reason", sa.String(200)),
        sa.Column(
            "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("agent_session_id", "client_request_id", name="uq_agent_run_request"),
    )
    op.create_index("ix_agent_runs_agent_session_id", "agent_runs", ["agent_session_id"])
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])
    op.create_table(
        "agent_events",
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("event_id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("agent_events")
    op.drop_index("ix_agent_runs_session_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_session_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agent_sessions_session_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")
