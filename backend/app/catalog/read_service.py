"""Deterministic queries over a frozen published dataset; never query an unpublished row."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.catalog.read_contracts import FactView, OfferView, PricedLine
from app.ingestion import models as ingestion
from app.ingestion.contracts import ImportRow
from app.profiles.service import DomainError


def encode_cursor(version, key, identifier):
    data = json.dumps([str(version), key, str(identifier)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode_cursor(value, version):
    try:
        padded = value + "=" * (-len(value) % 4)
        cursor_version, key, identifier = json.loads(base64.urlsafe_b64decode(padded))
        if UUID(cursor_version) != version or not isinstance(key, str):
            raise ValueError
        return key, UUID(identifier)
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise DomainError(422, "INVALID_CURSOR", "目录翻页令牌无效或已过期。") from None


class CatalogReadService:
    def __init__(self, engine, settings, clock=None):
        self.engine, self.settings = engine, settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def synthetic_namespace(self):
        database = make_url(self.settings.database_url.get_secret_value()).database or ""
        return self.settings.app_env == "test" and database.startswith("test_")

    def _version(self, conn):
        synthetic = self.synthetic_namespace()
        version = conn.scalar(
            select(ingestion.pointers.c.version_id).where(
                ingestion.pointers.c.synthetic.is_(synthetic)
            )
        )
        if version is None:
            return None, []
        records = conn.scalar(
            select(ingestion.versions.c.records).where(
                ingestion.versions.c.id == version, ingestion.versions.c.synthetic.is_(synthetic)
            )
        )
        if records is None:
            raise DomainError(503, "CATALOG_VERSION_INVALID", "当前目录版本不可用。")
        return version, [ImportRow.model_validate(record) for record in records]

    def current_version(self):
        with self.engine.connect() as conn:
            version, _ = self._version(conn)
        return version

    def knowledge_document_reference(self, source_document_id):
        """Return only a published document whose source permits stored public excerpts."""
        with self.engine.connect() as conn:
            version, records = self._version(conn)
        if version is None:
            raise DomainError(404, "SOURCE_DOCUMENT_NOT_FOUND", "来源文档不存在或尚未发布。")
        index = self._index(records)
        document = index.get("source_documents", {}).get(str(source_document_id))
        source = index.get("sources", {}).get(str(document["source_id"])) if document else None
        if (
            not document
            or not source
            or source["permission_status"] not in {"allowed", "restricted"}
            or not {"public_display", "excerpt_storage"}.issubset(source["allowed_uses"])
        ):
            raise DomainError(
                404, "SOURCE_DOCUMENT_NOT_FOUND", "来源文档不存在或未获片段展示许可。"
            )
        return {
            "data_version": version,
            "title": document["title"],
            "canonical_url": document["canonical_url"],
        }

    @staticmethod
    def _index(records):
        indexed = {}
        for record in records:
            indexed.setdefault(record.kind, {})[str(record.data.get("id", ""))] = record.data
        return indexed

    def _public_source(self, index, source_id):
        source = index.get("sources", {}).get(str(source_id))
        return (
            source
            if source
            and source["permission_status"] in {"allowed", "restricted"}
            and "public_display" in source["allowed_uses"]
            else None
        )

    def _evidence(self, index, evidence_id):
        evidence = index.get("evidence", {}).get(str(evidence_id))
        if not evidence or evidence["review_status"] != "approved":
            return None
        document = index.get("source_documents", {}).get(str(evidence["document_id"]))
        source = self._public_source(index, document["source_id"]) if document else None
        if not document or not source:
            return None
        return {
            "source_name": source["name"],
            "source_domain": source["domain"],
            "document_title": document["title"],
            "canonical_url": document["canonical_url"],
            "document_hash": document["content_sha256"],
            "fetched_at": document["fetched_at"],
            "locator_kind": evidence["locator_kind"],
            "locator": evidence["locator"],
            "excerpt_hash": evidence["excerpt_sha256"],
        }

    def _summary(self, index, sku, version, now):
        brand = index["brands"].get(str(sku["brand_id"]))
        family = index["product_families"].get(str(sku["family_id"]))
        if not brand or not family or sku["identity_status"] != "verified":
            return None
        facts = [
            fact
            for fact in index.get("spec_facts", {}).values()
            if fact["sku_id"] == sku["id"]
            and fact["valid_from"] <= now.isoformat().replace("+00:00", "Z")
            and (
                fact["valid_to"] is None
                or fact["valid_to"] > now.isoformat().replace("+00:00", "Z")
            )
        ]
        return {
            "id": sku["id"],
            "record_key": sku["record_key"],
            "category": sku["category"],
            "region": sku["region"],
            "brand": brand["name"],
            "family": family["name"],
            "manufacturer_part_number": sku["manufacturer_part_number"],
            "status": sku["status"],
            "data_version": version,
            "missing_key_facts": not bool(facts),
        }

    def list_products(self, category=None, region=None, query=None, cursor=None, limit=20):
        now = self.clock()
        with self.engine.connect() as conn:
            version, records = self._version(conn)
        if version is None:
            return {
                "items": [],
                "next_cursor": None,
                "data_version": None,
                "generated_at": now,
                "empty_reason": "no_published_catalog",
            }
        index = self._index(records)
        aliases = index.get("product_aliases", {}).values()
        normalized_query = query.strip().lower() if query else None
        products = []
        for sku in index.get("product_skus", {}).values():
            item = self._summary(index, sku, version, now)
            if (
                item is None
                or (category and item["category"] != category)
                or (region and item["region"] != region)
            ):
                continue
            searchable = " ".join(
                filter(
                    None,
                    [
                        item["brand"],
                        item["family"],
                        item["manufacturer_part_number"],
                        item["record_key"],
                    ],
                )
            )
            searchable += " " + " ".join(
                alias["alias"] for alias in aliases if alias["sku_id"] == sku["id"]
            )
            if normalized_query and normalized_query not in searchable.lower():
                continue
            products.append(item)
        products.sort(key=lambda item: (item["record_key"], item["id"]))
        if cursor:
            last_key, last_id = decode_cursor(cursor, version)
            products = [
                item
                for item in products
                if (item["record_key"], UUID(item["id"])) > (last_key, last_id)
            ]
        selected = products[:limit]
        next_cursor = (
            encode_cursor(version, selected[-1]["record_key"], selected[-1]["id"])
            if len(products) > limit
            else None
        )
        return {
            "items": selected,
            "next_cursor": next_cursor,
            "data_version": version,
            "generated_at": now,
            "empty_reason": None,
        }

    def product(self, sku_id):
        now = self.clock()
        with self.engine.connect() as conn:
            version, records = self._version(conn)
            canonical = (
                conn.execute(
                    select(ingestion.canonical).where(ingestion.canonical.c.version_id == version)
                    if version
                    else select(ingestion.canonical).where(False)
                )
                .mappings()
                .all()
            )
        if version is None:
            raise DomainError(404, "PRODUCT_NOT_FOUND", "商品不存在或尚未发布。")
        index = self._index(records)
        sku = index.get("product_skus", {}).get(str(sku_id))
        summary = self._summary(index, sku, version, now) if sku else None
        if summary is None:
            raise DomainError(404, "PRODUCT_NOT_FOUND", "商品不存在或尚未发布。")
        canon = {str(row["fact_id"]) for row in canonical}
        facts = []
        for fact in index.get("spec_facts", {}).values():
            if (
                fact["sku_id"] != sku["id"]
                or fact["id"] not in canon
                or fact["valid_from"] > now.isoformat().replace("+00:00", "Z")
            ):
                continue
            if fact["valid_to"] and fact["valid_to"] <= now.isoformat().replace("+00:00", "Z"):
                continue
            attribute = index["attribute_definitions"].get(str(fact["attribute_id"]))
            evidence = self._evidence(index, fact["evidence_id"])
            if not attribute or not evidence:
                continue
            value = fact.get("value_" + fact["value_type"])
            if fact["value_type"] == "decimal" and value is not None:
                value = str(value)
            facts.append(
                FactView(
                    id=fact["id"],
                    key=attribute["key"],
                    description=attribute["description"],
                    value_type=fact["value_type"],
                    value=value,
                    unit=fact["unit"],
                    raw_value=fact["raw_value"],
                    raw_unit=fact["raw_unit"],
                    missing_reason=fact["missing_reason"],
                    conditions=fact["conditions"],
                    valid_from=fact["valid_from"],
                    valid_to=fact["valid_to"],
                    evidence=evidence,
                ).model_dump()
            )
        aliases = sorted(
            alias["alias"]
            for alias in index.get("product_aliases", {}).values()
            if alias["sku_id"] == sku["id"]
        )
        return {
            **summary,
            "identity_status": sku["identity_status"],
            "revision_status": sku["revision_status"],
            "hardware_revision": sku["hardware_revision"],
            "configuration_fingerprint": sku["configuration_fingerprint"],
            "aliases": aliases,
            "facts": sorted(facts, key=lambda fact: (fact["key"], fact["id"])),
        }

    def _offer(self, index, offer, version, now):
        listing = index.get("merchant_listings", {}).get(str(offer["listing_id"]))
        merchant = index.get("merchants", {}).get(str(listing["merchant_id"])) if listing else None
        evidence = self._evidence(index, offer["evidence_id"])
        if (
            not listing
            or not merchant
            or not evidence
            or not self._public_source(index, listing["source_id"])
        ):
            return None
        fresh = offer["observed_at"] <= now.isoformat().replace("+00:00", "Z") < offer["expires_at"]
        age = (
            now - datetime.fromisoformat(offer["observed_at"].replace("Z", "+00:00"))
        ).total_seconds()
        fresh = fresh and age <= self.settings.price_max_age_seconds
        return OfferView(
            id=offer["id"],
            sku_id=offer["sku_id"],
            merchant_name=merchant["name"],
            platform=merchant["platform"],
            listing_url=listing["listing_url"],
            amount_minor=offer["amount_minor"],
            amount_missing_reason=offer["amount_missing_reason"],
            shipping_minor=offer["shipping_minor"],
            tax_minor=offer["tax_minor"],
            tax_included=offer["tax_included"],
            currency=offer["currency"],
            region=offer["region"],
            stock_status=offer["stock_status"],
            condition=offer["condition"],
            eligibility_type=offer["eligibility_type"],
            eligibility_details=offer["eligibility_details"],
            observed_at=offer["observed_at"],
            expires_at=offer["expires_at"],
            freshness="current" if fresh else "historical",
            evidence=evidence,
            data_version=version,
        ).model_dump()

    def offers(self, sku_id, region=None, include_historical=False):
        now = self.clock()
        with self.engine.connect() as conn:
            version, records = self._version(conn)
        if version is None:
            return {
                "items": [],
                "data_version": None,
                "generated_at": now,
                "empty_reason": "no_published_catalog",
            }
        index = self._index(records)
        items = [
            self._offer(index, offer, version, now)
            for offer in index.get("offer_snapshots", {}).values()
            if offer["sku_id"] == str(sku_id) and (region is None or offer["region"] == region)
        ]
        items = [
            item
            for item in items
            if item and (include_historical or item["freshness"] == "current")
        ]
        items.sort(key=lambda item: item["id"])
        items.sort(key=lambda item: item["observed_at"], reverse=True)
        items.sort(key=lambda item: item["freshness"] != "current")
        return {
            "items": items,
            "data_version": version,
            "generated_at": now,
            "empty_reason": None if items else "no_matching_offers",
        }

    def current_offers(self, sku_id, region):
        return [
            offer
            for offer in self.offers(sku_id, region)["items"]
            if offer["freshness"] == "current"
            and offer["stock_status"] == "in_stock"
            and offer["condition"] == "new"
            and offer["eligibility_type"] == "unconditional"
        ]


class ManualOfferProvider:
    """A provider for vetted manual snapshots only; it performs no network request."""

    def __init__(self, catalog):
        self.catalog = catalog

    def offers(self, sku_id, region):
        return self.catalog.current_offers(sku_id, region)


class PriceService:
    def __init__(self, catalog, clock=None):
        self.catalog, self.clock = catalog, clock or catalog.clock

    def quote(self, request):
        now = self.clock()
        provider, lines, expiry = ManualOfferProvider(self.catalog), [], []
        version = None
        for item in request.items:
            self.catalog.product(item.sku_id)
            offers = provider.offers(item.sku_id, request.region)
            version = (
                self.catalog.offers(item.sku_id, request.region)["data_version"]
                if version is None
                else version
            )
            selected = (
                next((offer for offer in offers if offer["id"] == item.offer_id), None)
                if item.offer_id
                else (offers[0] if offers else None)
            )
            if item.offer_id is not None and selected is None:
                raise DomainError(
                    422, "OFFER_NOT_AVAILABLE", "指定报价不属于当前可获得的 SKU、地区或资格。"
                )
            reasons, known = [], 0
            if not selected:
                reasons.append("NO_CURRENT_OFFER")
                lines.append(
                    PricedLine(
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        offer_id=None,
                        amount_minor=None,
                        shipping_minor=None,
                        tax_minor=None,
                        tax_included=None,
                        known_total_minor=0,
                        unpriced_reasons=reasons,
                        expires_at=None,
                    ).model_dump()
                )
                continue
            if selected["amount_minor"] is None:
                reasons.append("PRICE_UNKNOWN")
            else:
                known += selected["amount_minor"] * item.quantity
            if selected["shipping_minor"] is None:
                reasons.append("SHIPPING_UNKNOWN")
            else:
                known += selected["shipping_minor"]
            if selected["tax_included"] is True:
                pass
            elif selected["tax_minor"] is None:
                reasons.append("TAX_UNKNOWN")
            else:
                known += selected["tax_minor"]
            expiry.append(selected["expires_at"])
            lines.append(
                PricedLine(
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    offer_id=selected["id"],
                    amount_minor=selected["amount_minor"],
                    shipping_minor=selected["shipping_minor"],
                    tax_minor=selected["tax_minor"],
                    tax_included=selected["tax_included"],
                    known_total_minor=known,
                    unpriced_reasons=reasons,
                    expires_at=selected["expires_at"],
                ).model_dump()
            )
        known = sum(line["known_total_minor"] for line in lines)
        complete = not any(line["unpriced_reasons"] for line in lines)
        total = known if complete else None
        return {
            "data_version": version,
            "lines": lines,
            "known_subtotal_minor": known,
            "total_minor": total,
            "price_complete": complete,
            "budget_minor": request.budget_minor,
            "budget_satisfied": total <= request.budget_minor
            if total is not None and request.budget_minor is not None
            else None,
            "expires_at": min(expiry) if expiry else None,
            "generated_at": now,
        }
