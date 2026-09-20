from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
sessions = Table(
    "anonymous_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
)
profiles = Table(
    "profiles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("revision", Integer, nullable=False),
)
revisions = Table(
    "profile_revisions",
    metadata,
    Column(
        "profile_id",
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("revision", Integer, primary_key=True),
    Column("profile", JSONB, nullable=False),
    Column("origins", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
limits = Table(
    "request_limits",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("window", Integer, primary_key=True),
    Column("count", Integer, nullable=False),
)
