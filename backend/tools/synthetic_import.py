"""Reproducible TEST-only manual fixture. Never a real product or authorized data source."""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5


def example():
    rows = []
    ids = {
        name: str(uuid5(NAMESPACE_URL, "TEST-T03/" + name))
        for name in (
            "brand",
            "family",
            "sku",
            "source",
            "document",
            "evidence",
            "attribute",
            "fact",
            "merchant",
            "listing",
            "offer",
        )
    }
    when = "2026-01-01T00:00:00Z"

    def add(kind, label, **fields):
        rows.append(
            {
                "kind": kind,
                "data": dict(
                    id=ids[label], record_key="TEST-T03-" + label, synthetic=True, **fields
                ),
            }
        )

    add("brands", "brand", name="TEST-BRAND")
    add("product_families", "family", brand_id=ids["brand"], category="cpu", name="TEST-FAMILY")
    add(
        "sources",
        "source",
        name="TEST-SOURCE",
        domain="test.example",
        source_type="manual",
        access_method="manual",
        permission_status="allowed",
        permission_evidence="TEST-only permission fixture, no real authorization",
        terms_checked_at=when,
        allowed_uses=["internal_review", "public_display"],
    )
    add(
        "source_documents",
        "document",
        source_id=ids["source"],
        canonical_url="https://test.example/spec",
        title="TEST synthetic document",
        content_sha256=hashlib.sha256(b"TEST count=8").hexdigest(),
        fetched_at=when,
        parser_version="TEST-manual-v1",
    )
    add(
        "evidence",
        "evidence",
        document_id=ids["document"],
        locator_kind="section",
        locator="TEST-count",
        excerpt_sha256=hashlib.sha256(b"TEST count=8").hexdigest(),
    )
    add(
        "product_skus",
        "sku",
        family_id=ids["family"],
        brand_id=ids["brand"],
        category="cpu",
        region="CN",
        manufacturer_part_number="TEST-PN",
        revision_status="not_applicable",
        identity_status="verified",
        identity_evidence_id=ids["evidence"],
    )
    rows.append(
        {
            "kind": "evidence_skus",
            "data": dict(evidence_id=ids["evidence"], sku_id=ids["sku"], synthetic=True),
        }
    )
    add(
        "attribute_definitions",
        "attribute",
        key="test_count",
        category="cpu",
        value_type="integer",
        canonical_unit="count",
        description="TEST-only count",
    )
    add(
        "spec_facts",
        "fact",
        sku_id=ids["sku"],
        attribute_id=ids["attribute"],
        evidence_id=ids["evidence"],
        category="cpu",
        value_type="integer",
        unit="count",
        value_integer=8,
        raw_value="8",
        valid_from=when,
    )
    add(
        "merchants",
        "merchant",
        name="TEST-MERCHANT",
        platform="TEST-PLATFORM",
        external_seller_id="TEST-SELLER",
    )
    add(
        "merchant_listings",
        "listing",
        merchant_id=ids["merchant"],
        source_id=ids["source"],
        external_listing_id="TEST-LISTING",
        listing_url="https://test.example/listing",
        matched_sku_id=ids["sku"],
        match_evidence_id=ids["evidence"],
        match_status="matched",
    )
    add(
        "offer_snapshots",
        "offer",
        listing_id=ids["listing"],
        sku_id=ids["sku"],
        evidence_id=ids["evidence"],
        amount_minor=123456,
        shipping_minor=0,
        tax_included=True,
        tax_minor=0,
        currency="CNY",
        region="CN",
        observed_at=when,
        expires_at="2026-01-02T00:00:00Z",
        stock_status="in_stock",
        condition="new",
        eligibility_type="unconditional",
    )
    return dict(
        format_version="manual-v1",
        source_id=ids["source"],
        external_batch_id="TEST-T03-BATCH",
        synthetic=True,
        rows=rows,
        configurations={},
    )


if __name__ == "__main__":
    print(json.dumps(example(), ensure_ascii=False, indent=2))
