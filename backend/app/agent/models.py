from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

agent_sessions = Table(
    "agent_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("revision", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
agent_runs = Table(
    "agent_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "agent_session_id",
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "profile_id",
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("profile_revision", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("message", Text(), nullable=False),
    Column("client_request_id", String(200), nullable=False),
    Column("body_hash", String(64), nullable=False),
    Column("status", String(24), nullable=False),
    Column("answer", JSONB()),
    Column("pending_question", String(500)),
    Column("reason", String(200)),
    Column("cancel_requested", Boolean(), nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    UniqueConstraint("agent_session_id", "client_request_id", name="uq_agent_run_request"),
)
agent_events = Table(
    "agent_events",
    metadata,
    Column(
        "run_id",
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("event_id", Integer(), primary_key=True),
    Column("revision", Integer(), nullable=False),
    Column("type", String(32), nullable=False),
    Column("data", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
