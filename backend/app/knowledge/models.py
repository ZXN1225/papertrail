from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
documents = Table(
    "knowledge_documents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source_document_id", UUID(as_uuid=True), nullable=False),
    Column("data_version", UUID(as_uuid=True), nullable=False),
    Column("title", String(500), nullable=False),
    Column("canonical_url", String(2000), nullable=False),
    Column("language", String(20), nullable=False),
    Column("region", String(2)),
    Column("sku_ids", JSONB, nullable=False),
    Column("content_sha256", String(64), nullable=False, unique=True),
    Column("review_status", String(12), nullable=False),
    Column("reviewer", String(120)),
    Column("review_note", String(1000)),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "document_id",
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("locator", String(120), nullable=False),
    Column("content", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
)
