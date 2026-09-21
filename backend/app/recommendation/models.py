"""Immutable, owner-scoped recommendation snapshots."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
snapshots = Table(
    "recommendation_snapshots",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("lineage_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("parent_id", UUID(as_uuid=True), ForeignKey("recommendation_snapshots.id")),
    Column("revision", Integer, nullable=False),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "profile_id",
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("profile_revision", Integer, nullable=False),
    Column("mode", String(12), nullable=False),
    Column("request", JSONB, nullable=False),
    Column("result", JSONB, nullable=False),
    Column("data_version", UUID(as_uuid=True)),
    Column("expires_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
idempotency = Table(
    "recommendation_idempotency",
    metadata,
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("path", String(160), primary_key=True),
    Column("idempotency_key", String(200), primary_key=True),
    Column("body_hash", String(64), nullable=False),
    Column(
        "snapshot_id",
        UUID(as_uuid=True),
        ForeignKey("recommendation_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
