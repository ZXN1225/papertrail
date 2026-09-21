"""One bounded, transactional path shared by the manual CLI and admin HTTP API."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.catalog import contracts as c
from app.catalog import models as catalog
from app.ingestion import models as m
from app.ingestion.contracts import ImportInput, ImportJob, ImportRow, Issue, Preview, RowPreview
from app.profiles.service import DomainError

KINDS = (
    "brands",
    "product_families",
    "product_skus",
    "product_aliases",
    "sources",
    "source_documents",
    "evidence",
    "evidence_skus",
    "attribute_definitions",
    "spec_facts",
    "merchants",
    "merchant_listings",
    "offer_snapshots",
)
MODELS = dict(zip(KINDS, c.RECORD_MODELS, strict=True))
ORDER = (
    "brands",
    "product_families",
    "sources",
    "source_documents",
    "evidence",
    "attribute_definitions",
    "merchants",
    "product_skus",
    "product_aliases",
    "evidence_skus",
    "spec_facts",
    "merchant_listings",
    "offer_snapshots",
)


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identity(row):
    if row.kind == "evidence_skus":
        return (row.kind, row.data["evidence_id"], row.data["sku_id"])
    return (row.kind, row.data["id"])


def business(data):
    return {k: v for k, v in data.items() if k not in {"review_status", "reviewer", "reviewed_at"}}


def fact_group(data):
    return (data["sku_id"], data["attribute_id"], digest(data["conditions"]))


def configuration_fingerprint(value):
    required = {"cpu", "gpu", "memory", "storage", "display"}
    if set(value) != required or any(not v.strip() for v in value.values()):
        raise ValueError("CONFIGURATION_INCOMPLETE")
    normalized = {k: v.strip() for k, v in value.items()}
    return digest({"algorithm": "configuration-v1", "components": normalized})


def normalize(row, configurations):
    data = dict(row.data)
    # Input cannot mint audit identities; existing audit fields are excluded from comparison.
    if (
        data.get("review_status", "pending") != "pending"
        or data.get("reviewer")
        or data.get("reviewed_at")
    ):
        raise ValueError("CLIENT_REVIEW_FORBIDDEN")
    if row.kind == "brands":
        data["normalized_name"] = str(data.get("name", "")).strip().lower()
    if row.kind == "product_aliases":
        data["normalized_alias"] = str(data.get("alias", "")).strip().lower()
    if row.kind == "product_skus":
        part = data.get("manufacturer_part_number")
        data["normalized_part_number"] = part.strip().lower() if isinstance(part, str) else None
        revision = data.get("hardware_revision")
        if isinstance(revision, str):
            data["hardware_revision"] = revision.strip().lower()
        if data.get("category") == "laptop":
            config = configurations.get(str(data.get("id")))
            if config is None:
                raise ValueError("CONFIGURATION_REQUIRED")
            expected = configuration_fingerprint(config)
            if data.get("configuration_fingerprint") not in {None, expected}:
                raise ValueError("CONFIGURATION_HASH_MISMATCH")
            data["configuration_fingerprint"] = expected
    if row.kind == "spec_facts" and data.get("raw_unit") not in {None, data.get("unit")}:
        factors = {("cm", "mm"): "10", ("m", "mm"): "1000", ("kg", "g"): "1000"}
        factor = factors.get((data.get("raw_unit"), data.get("unit")))
        if factor is None or data.get("value_type") not in {"integer", "decimal"}:
            raise ValueError("UNSUPPORTED_UNIT_CONVERSION")
        try:
            converted = Decimal(data["raw_value"]) * Decimal(factor)
            supplied = data.get("value_" + data["value_type"])
            if not converted.is_finite() or Decimal(str(supplied)) != converted:
                raise ValueError("NORMALIZED_VALUE_MISMATCH")
        except (InvalidOperation, KeyError, TypeError):
            raise ValueError("NORMALIZED_VALUE_MISMATCH") from None
    # No heuristic MHz/MT/s, GB/GiB, power or benchmark conversion.
    return MODELS[row.kind].model_validate(data)


class ImportService:
    def __init__(self, engine, settings, actor, clock=None):
        self.engine, self.settings, self.actor = engine, settings, actor
        self.clock = clock or (lambda: datetime.now(UTC))

    def _namespace(self, synthetic):
        if synthetic and (
            self.settings.app_env != "test"
            or not (
                make_url(self.settings.database_url.get_secret_value()).database or ""
            ).startswith("test_")
        ):
            raise DomainError(422, "SYNTHETIC_FORBIDDEN", "合成导入仅允许隔离 test_* 测试环境。")

    def _lock(self, conn, synthetic):
        conn.execute(
            text("SELECT pg_advisory_xact_lock(73303, :namespace)"), {"namespace": int(synthetic)}
        )

    def _current(self, conn, synthetic):
        return conn.scalar(
            select(m.pointers.c.version_id).where(m.pointers.c.synthetic == synthetic)
        )

    def _snapshot(self, conn, version):
        if version is None:
            return []
        rows = conn.scalar(select(m.versions.c.records).where(m.versions.c.id == version))
        return [ImportRow.model_validate(row) for row in rows]

    def _existing(self, conn, row):
        table = catalog.metadata.tables[row.kind]
        model = MODELS[row.kind].model_validate(row.data)
        values = model.model_dump()
        predicates = [table.c[col.name] == values[col.name] for col in table.primary_key]
        found = conn.execute(select(table).where(*predicates)).mappings().first()
        return (
            MODELS[row.kind].model_validate(dict(found)).model_dump(mode="json") if found else None
        )

    def _evaluate(self, conn, batch):
        conn.execute(text("SET CONSTRAINTS fk_sku_identity_evidence DEFERRED"))
        base = self._current(conn, batch.synthetic)
        normalized, issues, rows, seen = [], [], [], set()
        positions = {}
        for number, row in enumerate(batch.rows, 1):
            try:
                model = normalize(row, batch.configurations)
                if model.synthetic != batch.synthetic:
                    raise ValueError("NAMESPACE_MISMATCH")
                item = ImportRow(kind=row.kind, data=model.model_dump(mode="json"))
                key = identity(item)
                if key in seen:
                    raise ValueError("DUPLICATE_ROW")
                seen.add(key)
                positions[key] = number
                normalized.append(item)
            except (ValidationError, ValueError) as exc:
                field = (
                    ".".join(map(str, exc.errors()[0]["loc"]))
                    if isinstance(exc, ValidationError)
                    else ""
                )
                code = "INVALID_RECORD" if isinstance(exc, ValidationError) else str(exc)
                issues.append(
                    Issue(
                        row=number,
                        code=code,
                        field=field,
                        message="记录未通过校验，请按字段规范修正。",
                    )
                )
                rows.append(RowPreview(row=number, kind=row.kind, key="", action="invalid"))

        # Relational validation uses the real schema inside a rollback-only savepoint.
        sandbox = conn.begin_nested()
        try:
            for kind in ORDER:
                for row in (r for r in normalized if r.kind == kind):
                    number, key = positions[identity(row)], row.data.get("record_key", "scope")
                    action = "add"
                    try:
                        with conn.begin_nested():
                            existing = self._existing(conn, row)
                            if existing:
                                if business(existing) != business(row.data):
                                    raise ValueError("IMMUTABLE_RECORD_CONFLICT")
                                action = "unchanged"
                            else:
                                conn.execute(
                                    catalog.metadata.tables[kind]
                                    .insert()
                                    .values(**MODELS[kind].model_validate(row.data).model_dump())
                                )
                    except (IntegrityError, ValueError) as exc:
                        action = "invalid"
                        code = (
                            "RELATION_OR_CONSTRAINT"
                            if isinstance(exc, IntegrityError)
                            else str(exc)
                        )
                        issues.append(
                            Issue(row=number, code=code, message="引用、唯一性或不可覆盖记录冲突。")
                        )
                    rows.append(RowPreview(row=number, kind=kind, key=key, action=action))
            try:
                with conn.begin_nested():
                    conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            except IntegrityError:
                issues.append(
                    Issue(code="IDENTITY_EVIDENCE_SCOPE", message="身份依据缺失或不属于对应 SKU。")
                )
        finally:
            sandbox.rollback()
            conn.execute(text("SET CONSTRAINTS fk_sku_identity_evidence DEFERRED"))

        current_rows = self._snapshot(conn, base)
        for existing in current_rows:
            if self._existing(conn, existing) != existing.data:
                issues.append(
                    Issue(
                        code="PUBLISHED_RECORD_DRIFT",
                        message="已发布记录与冻结版本不一致，须排查数据库变更。",
                    )
                )
        merged = {identity(row): row for row in current_rows}
        merged.update({identity(row): row for row in normalized})
        all_rows = list(merged.values())
        gates, conflicts = self._gates(all_rows, batch, positions)
        valid = not issues
        issues.extend(gates)
        return Preview(
            content_hash=digest(batch.model_dump(mode="json")),
            base_version=base,
            rows=sorted(rows, key=lambda r: r.row),
            issues=issues,
            valid=valid,
            publishable=valid and not any(i.blocking for i in gates),
            normalized=normalized,
            conflict_groups=conflicts,
        )

    def _gates(self, rows, batch, positions):
        issues = []
        grouped = defaultdict(list)
        source_ids = set()
        now = self.clock()
        by_kind = defaultdict(list)
        for row in rows:
            by_kind[row.kind].append(row.data)
        for row in rows:
            data = row.data
            code = None
            # Existing database rows outside the published snapshot cannot silently join it.
            for constraint in catalog.metadata.tables[row.kind].foreign_key_constraints:
                local = [data[element.parent.name] for element in constraint.elements]
                if any(value is None for value in local):
                    continue
                target = constraint.elements[0].column.table.name
                names = [element.column.name for element in constraint.elements]
                if not any(
                    [candidate[name] for name in names] == local for candidate in by_kind[target]
                ):
                    issues.append(
                        Issue(
                            row=positions.get(identity(row)),
                            code="UNPUBLISHED_REFERENCE",
                            message="引用记录不在当前版本或本批次，不能隐式发布。",
                        )
                    )
            if row.kind == "sources":
                source_ids.add(data["id"])
                if data["permission_status"] not in {"allowed", "restricted"} or not {
                    "internal_review",
                    "public_display",
                } <= set(data["allowed_uses"]):
                    code = "SOURCE_PERMISSION_REQUIRED"
            elif row.kind in {"source_documents", "merchant_listings"}:
                if identity(row) in positions and data["source_id"] != str(batch.source_id):
                    code = "BATCH_SOURCE_MISMATCH"
                if row.kind == "source_documents" and data.get("storage_key"):
                    code = "RAW_STORAGE_NOT_SUPPORTED"
            elif row.kind == "product_skus" and data["identity_status"] != "verified":
                code = "SKU_IDENTITY_PENDING"
            elif row.kind == "merchant_listings" and data["match_status"] != "matched":
                code = "LISTING_MATCH_PENDING"
            elif row.kind == "spec_facts":
                grouped[fact_group(data)].append(data["id"])
                if data["missing_reason"]:
                    issues.append(
                        Issue(
                            row=positions.get(identity(row)),
                            code="MISSING_FACT",
                            message="事实值未知；发布不代表可用于完整推荐。",
                            blocking=False,
                        )
                    )
            elif row.kind == "offer_snapshots":
                earlier = [
                    offer
                    for offer in by_kind["offer_snapshots"]
                    if offer["id"] != data["id"]
                    and offer["listing_id"] == data["listing_id"]
                    and offer["currency"] == data["currency"]
                    and offer["eligibility_type"] == data["eligibility_type"]
                    and offer["observed_at"] <= data["observed_at"]
                    and offer["amount_minor"] is not None
                ]
                if earlier and data["amount_minor"] is not None and identity(row) in positions:
                    previous = max(earlier, key=lambda offer: (offer["observed_at"], offer["id"]))
                    if (
                        abs(data["amount_minor"] - previous["amount_minor"]) * 100
                        > previous["amount_minor"] * 30
                    ):
                        issues.append(
                            Issue(
                                row=positions[identity(row)],
                                code="PRICE_CHANGE_REVIEW",
                                message="同 listing 报价变化超过 30%，请在审核说明中核对原因。",
                                blocking=False,
                            )
                        )
                if datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")) <= now:
                    issues.append(
                        Issue(
                            row=positions.get(identity(row)),
                            code="HISTORICAL_OFFER",
                            message="报价已过期，仅可作为历史记录。",
                            blocking=False,
                        )
                    )
                if any(
                    data[key] is None for key in ("amount_minor", "shipping_minor", "tax_included")
                ):
                    issues.append(
                        Issue(
                            row=positions.get(identity(row)),
                            code="INCOMPLETE_PRICE",
                            message="报价费用不完整，不能宣称预算达成。",
                            blocking=False,
                        )
                    )
            if (
                row.kind in {"evidence", "spec_facts", "offer_snapshots"}
                and data.get("review_status") == "rejected"
            ):
                code = "REJECTED_RECORD"
            if row.kind in {"source_documents", "offer_snapshots"}:
                time_key = "fetched_at" if row.kind == "source_documents" else "observed_at"
                when = datetime.fromisoformat(data[time_key].replace("Z", "+00:00"))
                if when > now:
                    code = "FUTURE_OBSERVATION"
            if code:
                issues.append(
                    Issue(
                        row=positions.get(identity(row)),
                        code=code,
                        message="发布条件未满足，须补全资料或使用权限。",
                    )
                )
        if str(batch.source_id) not in source_ids:
            issues.append(
                Issue(code="BATCH_SOURCE_MISSING", message="批次来源必须存在于当前版本或本批中。")
            )
        conflicts = [ids for ids in grouped.values() if len(ids) > 1]
        for ids in conflicts:
            issues.append(
                Issue(
                    code="FACT_CONFLICT",
                    field=",".join(ids),
                    message="同属性及条件存在多条声明，审核时必须明确选择一条。",
                )
            )
        if not any(r.kind == "product_skus" for r in rows):
            issues.append(Issue(code="NO_SKU", message="发布版本至少包含一个已确认 SKU。"))
        return issues, conflicts

    def preview(self, batch):
        self._namespace(batch.synthetic)
        with self.engine.begin() as conn:
            self._lock(conn, batch.synthetic)
            return self._evaluate(conn, batch)

    def stage(self, batch):
        self._namespace(batch.synthetic)
        content_hash = digest(batch.model_dump(mode="json"))
        with self.engine.begin() as conn:
            self._lock(conn, batch.synthetic)
            existing = (
                conn.execute(
                    select(m.jobs).where(
                        m.jobs.c.source_id == batch.source_id,
                        m.jobs.c.external_batch_id == batch.external_batch_id,
                        m.jobs.c.synthetic == batch.synthetic,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["content_hash"] != content_hash:
                    raise DomainError(409, "BATCH_KEY_REUSED", "批号已用于不同内容，请使用新批号。")
                return self._job(existing)
            preview = self._evaluate(conn, batch)
            values = dict(
                id=uuid4(),
                source_id=batch.source_id,
                external_batch_id=batch.external_batch_id,
                synthetic=batch.synthetic,
                content_hash=content_hash,
                raw_snapshot=batch.model_dump(mode="json"),
                preview=preview.model_dump(mode="json"),
                status="staged" if preview.valid else "invalid",
                checkpoint="validated",
                created_by=self.actor,
                created_at=self.clock(),
            )
            row = conn.execute(m.jobs.insert().values(**values).returning(m.jobs)).mappings().one()
            return self._job(row)

    def _job(self, row):
        return ImportJob.model_validate({key: row[key] for key in ImportJob.model_fields})

    def _load(self, conn, job_id, lock=False):
        query = select(m.jobs).where(m.jobs.c.id == job_id)
        if lock:
            query = query.with_for_update()
        row = conn.execute(query).mappings().first()
        if row is None:
            raise DomainError(404, "IMPORT_NOT_FOUND", "导入任务不存在。")
        self._namespace(row["synthetic"])
        return row

    def get(self, job_id):
        with self.engine.connect() as conn:
            return self._job(self._load(conn, job_id))

    def _expected(self, row, request, current):
        stored_base = (
            UUID(row["preview"]["base_version"]) if row["preview"]["base_version"] else None
        )
        if request.content_hash != row["content_hash"] or request.base_version != stored_base:
            raise DomainError(409, "STALE_REVIEW", "审核内容或父版本不匹配。")
        if current != request.base_version:
            raise DomainError(
                409, "DATA_VERSION_CHANGED", "已发布数据已变化，请用新批号重新预览审核。"
            )

    def _selections(self, rows, selected):
        groups = defaultdict(list)
        for row in rows:
            if row.kind == "spec_facts":
                groups[fact_group(row.data)].append(row)
        requested = {str(value) for value in selected}
        known = {row.data["id"] for group in groups.values() for row in group}
        if not requested <= known or len(requested) != len(selected):
            raise DomainError(422, "INVALID_FACT_SELECTION", "事实选择包含重复或未知 ID。")
        chosen = []
        for group in groups.values():
            picks = [row for row in group if row.data["id"] in requested]
            if len(group) == 1:
                chosen.append(group[0])
            elif len(picks) == 1:
                chosen.extend(picks)
            else:
                raise DomainError(422, "UNRESOLVED_CONFLICT", "每组冲突必须明确选择一个事实。")
        return chosen

    def _candidate(self, conn, preview):
        merged = {identity(r): r for r in self._snapshot(conn, preview.base_version)}
        merged.update({identity(r): r for r in preview.normalized})
        return list(merged.values())

    def review(self, job_id, request):
        with self.engine.begin() as conn:
            initial = self._load(conn, job_id)
            self._lock(conn, initial["synthetic"])
            row = self._load(conn, job_id, lock=True)
            if row["status"] not in {"staged", "invalid"}:
                raise DomainError(409, "IMPORT_STATE", "任务已审核，修改需新建批次。")
            self._expected(row, request, self._current(conn, row["synthetic"]))
            if request.decision == "approve":
                preview = self._evaluate(conn, ImportInput.model_validate(row["raw_snapshot"]))
                if not preview.valid or any(
                    i.blocking and i.code != "FACT_CONFLICT" for i in preview.issues
                ):
                    raise DomainError(422, "PUBLICATION_BLOCKED", "批次仍有阻断问题，不可批准。")
                self._selections(self._candidate(conn, preview), request.selected_fact_ids)
            result = (
                conn.execute(
                    update(m.jobs)
                    .where(m.jobs.c.id == job_id)
                    .values(
                        status="approved" if request.decision == "approve" else "rejected",
                        checkpoint="reviewed",
                        reviewer=self.actor,
                        review_note=request.note,
                        reviewed_at=self.clock(),
                        selected_fact_ids=[str(value) for value in request.selected_fact_ids],
                    )
                    .returning(m.jobs)
                )
                .mappings()
                .one()
            )
            return self._job(result)

    def publish(self, job_id, request):
        with self.engine.begin() as conn:
            initial = self._load(conn, job_id)
            self._lock(conn, initial["synthetic"])
            row = self._load(conn, job_id, lock=True)
            if row["status"] == "published":
                if request.content_hash != row["content_hash"] or request.base_version != (
                    UUID(row["preview"]["base_version"]) if row["preview"]["base_version"] else None
                ):
                    raise DomainError(409, "STALE_REVIEW", "请求与已发布批次不匹配。")
                snapshot = self._snapshot(conn, row["version_id"])
                return dict(
                    version_id=row["version_id"],
                    synthetic=row["synthetic"],
                    record_count=len(snapshot),
                )
            if row["status"] != "approved":
                raise DomainError(409, "REVIEW_REQUIRED", "只有已批准批次可发布。")
            self._expected(row, request, self._current(conn, row["synthetic"]))
            batch = ImportInput.model_validate(row["raw_snapshot"])
            preview = self._evaluate(conn, batch)
            if not preview.valid or any(
                i.blocking and i.code != "FACT_CONFLICT" for i in preview.issues
            ):
                raise DomainError(422, "PUBLICATION_BLOCKED", "发布重验失败，未修改当前版本。")
            candidate = self._candidate(conn, preview)
            chosen = self._selections(candidate, row["selected_fact_ids"])
            for kind in ORDER:
                for record in (r for r in preview.normalized if r.kind == kind):
                    if self._existing(conn, record) is None:
                        data = MODELS[kind].model_validate(record.data).model_dump()
                        if "review_status" in data:
                            data.update(
                                review_status="approved",
                                reviewer=row["reviewer"],
                                reviewed_at=row["reviewed_at"],
                            )
                        conn.execute(catalog.metadata.tables[kind].insert().values(**data))
            conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            # Snapshot actual rows including server-derived review metadata, never mutable pointers.
            actual = [ImportRow(kind=r.kind, data=self._existing(conn, r)) for r in candidate]
            serialized = [r.model_dump(mode="json") for r in actual]
            version = uuid4()
            conn.execute(
                m.versions.insert().values(
                    id=version,
                    job_id=job_id,
                    parent_id=preview.base_version,
                    synthetic=batch.synthetic,
                    records=serialized,
                    content_hash=digest(serialized),
                    published_by=self.actor,
                    published_at=self.clock(),
                )
            )
            for fact in chosen:
                values = MODELS["spec_facts"].model_validate(fact.data).model_dump()
                fields = {
                    key: values[key]
                    for key in (
                        "sku_id",
                        "attribute_id",
                        "value_type",
                        "unit",
                        "value_text",
                        "value_integer",
                        "value_decimal",
                        "value_boolean",
                        "missing_reason",
                        "conditions",
                    )
                }
                conn.execute(
                    m.canonical.insert().values(
                        version_id=version,
                        fact_id=values["id"],
                        synthetic=batch.synthetic,
                        conditions_hash=digest(fact.data["conditions"]),
                        **fields,
                    )
                )
            conn.execute(
                insert(m.pointers)
                .values(synthetic=batch.synthetic, version_id=version)
                .on_conflict_do_update(index_elements=["synthetic"], set_={"version_id": version})
            )
            self._enqueue(conn, version)
            conn.execute(
                update(m.jobs)
                .where(m.jobs.c.id == job_id)
                .values(status="published", checkpoint="published", version_id=version)
            )
            return dict(version_id=version, synthetic=batch.synthetic, record_count=len(actual))

    def _enqueue(self, conn, version):
        conn.execute(
            m.outbox.insert().values(id=uuid4(), version_id=version, next_run_at=self.clock())
        )

    def dispatch(self, limit=20, consumer=None):
        """Lease/retry delivery into a durable notification inbox; no fake external index update."""
        delivered = failed = 0
        for _ in range(min(max(limit, 1), 100)):
            now, lease = self.clock(), uuid4()
            with self.engine.begin() as conn:
                row = (
                    conn.execute(
                        select(m.outbox)
                        .join(m.versions, m.outbox.c.version_id == m.versions.c.id)
                        .where(
                            m.versions.c.synthetic.is_(False)
                            if not (
                                self.settings.app_env == "test"
                                and (
                                    make_url(self.settings.database_url.get_secret_value()).database
                                    or ""
                                ).startswith("test_")
                            )
                            else text("TRUE"),
                            m.outbox.c.status != "delivered",
                            m.outbox.c.next_run_at <= now,
                            (m.outbox.c.lease_until.is_(None) | (m.outbox.c.lease_until <= now)),
                        )
                        .order_by(m.outbox.c.next_run_at, m.outbox.c.id)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    break
                conn.execute(
                    update(m.outbox)
                    .where(m.outbox.c.id == row["id"])
                    .values(
                        status="leased",
                        lease_id=lease,
                        lease_until=now + timedelta(seconds=30),
                        attempts=row["attempts"] + 1,
                    )
                )
            try:
                if consumer:
                    consumer(row["version_id"])
                with self.engine.begin() as conn:
                    owned = (
                        conn.execute(
                            select(m.outbox)
                            .where(m.outbox.c.id == row["id"], m.outbox.c.lease_id == lease)
                            .with_for_update()
                        )
                        .mappings()
                        .first()
                    )
                    if owned is None:
                        continue
                    conn.execute(
                        insert(m.notifications)
                        .values(version_id=row["version_id"], delivered_at=self.clock())
                        .on_conflict_do_nothing(index_elements=["version_id"])
                    )
                    conn.execute(
                        update(m.outbox)
                        .where(m.outbox.c.id == row["id"])
                        .values(
                            status="delivered", lease_id=None, lease_until=None, last_error=None
                        )
                    )
                delivered += 1
            except Exception:
                with self.engine.begin() as conn:
                    conn.execute(
                        update(m.outbox)
                        .where(m.outbox.c.id == row["id"], m.outbox.c.lease_id == lease)
                        .values(
                            status="pending",
                            lease_id=None,
                            lease_until=None,
                            last_error="DELIVERY_FAILED",
                            next_run_at=self.clock()
                            + timedelta(seconds=min(300, 2 ** min(row["attempts"] + 1, 8))),
                        )
                    )
                failed += 1
        return dict(delivered=delivered, failed=failed)
