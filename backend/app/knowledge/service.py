"""Manual reviewed-document ingest and deterministic BM25 retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update

from app.knowledge import models
from app.profiles.service import DomainError


def tokenize(value):
    tokens = []
    for part in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", value.casefold()):
        if part.isascii():
            tokens.append(part)
        elif len(part) == 1:
            tokens.append(part)
        else:
            tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
    return tokens


def bm25(query, chunks):
    terms = tokenize(query)
    if not terms or not chunks:
        return []
    lengths = [max(1, len(tokenize(item["content"]))) for item in chunks]
    average = sum(lengths) / len(lengths)
    document_frequency = Counter(
        term for term in set(terms) for item in chunks if term in set(tokenize(item["content"]))
    )
    scored = []
    for item, length in zip(chunks, lengths, strict=True):
        frequencies = Counter(tokenize(item["content"]))
        score = 0.0
        for term in terms:
            if not frequencies[term]:
                continue
            inverse = math.log(
                1
                + (len(chunks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
            )
            score += (
                inverse
                * frequencies[term]
                * 2.2
                / (frequencies[term] + 1.2 * (1 - 0.75 + 0.75 * length / average))
            )
        if score > 0:
            scored.append((score, item))
    return sorted(scored, key=lambda value: (-value[0], str(value[1]["id"])))


class KnowledgeService:
    CHUNK_CHARS = 2400
    OVERLAP_CHARS = 240

    def __init__(self, engine, catalog, actor=None):
        self.engine, self.catalog, self.actor = engine, catalog, actor

    @staticmethod
    def _view(row):
        return {
            key: row[key]
            for key in (
                "id",
                "source_document_id",
                "data_version",
                "title",
                "canonical_url",
                "language",
                "region",
                "sku_ids",
                "content_sha256",
                "review_status",
                "reviewer",
                "reviewed_at",
                "created_at",
            )
        }

    @classmethod
    def _chunks(cls, content):
        text = "\n".join(line.strip() for line in content.splitlines() if line.strip())
        if not text:
            raise DomainError(422, "KNOWLEDGE_CONTENT_EMPTY", "文档不包含可检索文本。")
        start, ordinal, chunks = 0, 1, []
        while start < len(text):
            end = min(len(text), start + cls.CHUNK_CHARS)
            if end < len(text):
                boundary = text.rfind("。", start, end)
                if boundary > start + cls.CHUNK_CHARS // 2:
                    end = boundary + 1
            part = text[start:end]
            chunks.append((ordinal, f"chunk:{ordinal}", part, len(tokenize(part))))
            ordinal += 1
            if end == len(text):
                break
            start = max(start + 1, end - cls.OVERLAP_CHARS)
        return chunks

    def stage(self, body):
        reference = self.catalog.knowledge_document_reference(body.source_document_id)
        digest = hashlib.sha256(body.content.encode()).hexdigest()
        with self.engine.begin() as conn:
            existing = (
                conn.execute(
                    select(models.documents).where(models.documents.c.content_sha256 == digest)
                )
                .mappings()
                .first()
            )
            if existing:
                return self._view(existing)
            now, identifier = datetime.now(UTC), uuid4()
            row = {
                "id": identifier,
                "source_document_id": body.source_document_id,
                "data_version": reference["data_version"],
                "title": reference["title"],
                "canonical_url": reference["canonical_url"],
                "language": body.language,
                "region": body.region,
                "sku_ids": [str(item) for item in body.sku_ids],
                "content_sha256": digest,
                "review_status": "pending",
                "reviewer": None,
                "review_note": None,
                "reviewed_at": None,
                "created_at": now,
            }
            conn.execute(insert(models.documents).values(**row))
            conn.execute(
                insert(models.chunks),
                [
                    {
                        "id": uuid4(),
                        "document_id": identifier,
                        "ordinal": ordinal,
                        "locator": locator,
                        "content": content,
                        "token_count": count,
                    }
                    for ordinal, locator, content, count in self._chunks(body.content)
                ],
            )
            return self._view(row)

    def review(self, document_id, body):
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    select(models.documents)
                    .where(models.documents.c.id == document_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise DomainError(404, "KNOWLEDGE_DOCUMENT_NOT_FOUND", "知识文档不存在。")
            if row["review_status"] != "pending":
                raise DomainError(409, "KNOWLEDGE_ALREADY_REVIEWED", "知识文档已审核。")
            status = "approved" if body.decision == "approve" else "rejected"
            conn.execute(
                update(models.documents)
                .where(models.documents.c.id == document_id)
                .values(
                    review_status=status,
                    reviewer=self.actor,
                    review_note=body.note,
                    reviewed_at=datetime.now(UTC),
                )
            )
            return self._view(
                {
                    **row,
                    "review_status": status,
                    "reviewer": self.actor,
                    "reviewed_at": datetime.now(UTC),
                }
            )

    def search(self, body):
        version = self.catalog.current_version()
        if version is None:
            return {
                "status": "no_results",
                "citations": [],
                "missing_fields": ["no_published_catalog"],
                "data_version": None,
            }
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(models.chunks, models.documents)
                    .join(models.documents)
                    .where(
                        models.documents.c.review_status == "approved",
                        models.documents.c.data_version == version,
                    )
                )
                .mappings()
                .all()
            )
        selected = []
        requested = {str(item) for item in body.sku_ids}
        for row in rows:
            if body.region is not None and row["region"] not in {None, body.region}:
                continue
            if requested and not requested.intersection(set(row["sku_ids"])):
                continue
            selected.append(row)
        citations = [
            {
                "document_id": row["document_id"],
                "source_document_id": row["source_document_id"],
                "chunk_id": row["id"],
                "title": row["title"],
                "canonical_url": row["canonical_url"],
                "locator": row["locator"],
                "excerpt": row["content"],
                "score": round(score, 6),
                "data_version": version,
            }
            for score, row in bm25(body.query, selected)[: body.top_k]
        ]
        return {
            "status": "ok" if citations else "no_results",
            "citations": citations,
            "missing_fields": [] if citations else ["no_matching_reviewed_knowledge"],
            "data_version": version,
        }
