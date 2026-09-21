"""Persist deterministic recommendation outputs without mutating history."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select

from app.profiles.service import DomainError, invisible
from app.recommendation.contracts import (
    LaptopRankRequest,
    LaptopRankResponse,
    PcSolveRequest,
    PcSolveResponse,
)
from app.recommendation.models import idempotency, snapshots
from app.recommendation.pc_solver import PcSolver
from app.recommendation.service import LaptopRanker


class RecommendationSnapshotService:
    def __init__(self, engine, profile_service, catalog):
        self.engine = engine
        self.profiles = profile_service
        self.catalog = catalog

    @staticmethod
    def _hash(body):
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _total(result):
        candidates = result.get("candidates", [])
        return candidates[0].get("total_minor") if candidates else None

    def _snapshot(self, row):
        expiry = row["expires_at"]
        state = (
            "unknown"
            if expiry is None
            else "current"
            if expiry > datetime.now(UTC)
            else "historical"
        )
        return {
            "id": row["id"],
            "lineage_id": row["lineage_id"],
            "parent_id": row["parent_id"],
            "revision": row["revision"],
            "profile_id": row["profile_id"],
            "profile_revision": row["profile_revision"],
            "mode": row["mode"],
            "request": row["request"],
            "result": row["result"],
            "data_version": row["data_version"],
            "expires_at": expiry,
            "price_state": state,
            "created_at": row["created_at"],
        }

    def _run(self, mode, request):
        if mode == "laptop":
            parsed = LaptopRankRequest.model_validate(request)
            return LaptopRankResponse.model_validate(
                LaptopRanker(self.catalog).rank(parsed)
            ).model_dump(mode="json")
        parsed = PcSolveRequest.model_validate(request)
        return PcSolveResponse.model_validate(PcSolver(self.catalog).solve(parsed)).model_dump(
            mode="json"
        )

    def _expiry(self, mode, request, result):
        pairs = []
        for candidate in result.get("candidates", []):
            if mode == "laptop":
                pairs.append((candidate["sku_id"], candidate["offer_id"]))
            else:
                pairs.extend(
                    (item["sku_id"], item["offer_id"])
                    for item in candidate["items"]
                    if item["offer_id"] is not None
                )
        expiries = []
        for sku_id, offer_id in pairs:
            page = self.catalog.offers(sku_id, request.get("region", "CN"), include_historical=True)
            match = next((item for item in page["items"] if str(item["id"]) == str(offer_id)), None)
            if match is None:
                return None
            expiries.append(match["expires_at"])
        return min(expiries) if expiries else None

    def _owned(self, conn, cookie, snapshot_id):
        session = self.profiles.authenticate(conn, cookie, lock=True)
        row = (
            conn.execute(
                select(snapshots).where(
                    snapshots.c.id == snapshot_id, snapshots.c.session_id == session["id"]
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise invisible()
        return session, row

    def _save(self, session, source, request, result, body_hash, path):
        with self.engine.begin() as conn:
            existing = (
                conn.execute(
                    select(idempotency).where(
                        idempotency.c.session_id == session["id"],
                        idempotency.c.path == path,
                        idempotency.c.idempotency_key == source["idempotency_key"],
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["body_hash"] != body_hash:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能对应不同请求。")
                row = (
                    conn.execute(select(snapshots).where(snapshots.c.id == existing["snapshot_id"]))
                    .mappings()
                    .one()
                )
                return self._snapshot(row)
            now = datetime.now(UTC)
            snapshot_id = uuid4()
            lineage = source.get("lineage_id", snapshot_id)
            revision = source.get("revision", 1)
            data_version = result.get("data_version") or result.get("candidate_pool_version")
            row = {
                "id": snapshot_id,
                "lineage_id": lineage,
                "parent_id": source.get("parent_id"),
                "revision": revision,
                "session_id": session["id"],
                "profile_id": source["profile_id"],
                "profile_revision": source["profile_revision"],
                "mode": source["mode"],
                "request": request,
                "result": result,
                "data_version": data_version,
                "expires_at": self._expiry(source["mode"], request, result),
                "created_at": now,
            }
            conn.execute(insert(snapshots).values(**row))
            conn.execute(
                insert(idempotency).values(
                    session_id=session["id"],
                    path=path,
                    idempotency_key=source["idempotency_key"],
                    body_hash=body_hash,
                    snapshot_id=snapshot_id,
                    created_at=now,
                )
            )
            return self._snapshot(row)

    def create(self, cookie, body, idempotency_key):
        payload = body.model_dump(mode="json")
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            self.profiles.owned(conn, session, body.profile_id)
            self.profiles.snapshot(conn, body.profile_id, body.profile_revision)
        result = self._run(body.mode, payload["request"])
        return self._save(
            session,
            {
                "profile_id": body.profile_id,
                "profile_revision": body.profile_revision,
                "mode": body.mode,
                "idempotency_key": idempotency_key,
            },
            payload["request"],
            result,
            self._hash(payload),
            "/api/v1/recommendations",
        )

    def revise(self, cookie, recommendation_id, body, idempotency_key):
        payload = body.model_dump(mode="json")
        with self.engine.begin() as conn:
            session, previous = self._owned(conn, cookie, recommendation_id)
        result = self._run(previous["mode"], payload["request"])
        return self._save(
            session,
            {
                "profile_id": previous["profile_id"],
                "profile_revision": previous["profile_revision"],
                "mode": previous["mode"],
                "lineage_id": previous["lineage_id"],
                "parent_id": previous["id"],
                "revision": previous["revision"] + 1,
                "idempotency_key": idempotency_key,
            },
            payload["request"],
            result,
            self._hash(payload),
            f"/api/v1/recommendations/{recommendation_id}/revisions",
        )

    def read(self, cookie, recommendation_id):
        with self.engine.begin() as conn:
            _, row = self._owned(conn, cookie, recommendation_id)
            return self._snapshot(row)

    def compare(self, cookie, recommendation_ids):
        results = [self.read(cookie, recommendation_id) for recommendation_id in recommendation_ids]
        totals = [self._total(result["result"]) for result in results]
        base = totals[0]
        return {
            "recommendations": results,
            "price_differences_minor": [
                total - base if total is not None and base is not None else None for total in totals
            ],
        }

    def markdown(self, cookie, recommendation_id):
        snapshot = self.read(cookie, recommendation_id)
        total = self._total(snapshot["result"])
        lines = [
            "# 推荐方案快照",
            "",
            f"- 方案 ID：{snapshot['id']}",
            f"- 模式：{snapshot['mode']}",
            f"- 修订：{snapshot['revision']}",
            f"- 数据版本：{snapshot['data_version'] or '未知'}",
            f"- 报价状态：{snapshot['price_state']}",
            f"- 当前快照总价（分）：{total if total is not None else '未知'}",
            "",
            "结果以保存时的数据与报价为准；重新修订会创建新快照。",
        ]
        return "\n".join(lines) + "\n"
