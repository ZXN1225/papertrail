"""Strict record contracts, not public import endpoints or publication authorization."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.common.contracts import Contract

Category = Literal["cpu", "gpu", "motherboard", "memory", "ssd", "psu", "case", "cooler", "laptop"]
ValueType = Literal["text", "integer", "decimal", "boolean"]
Missing = Literal["not_collected", "not_disclosed", "conflicting", "not_applicable"]
Nonempty = Annotated[StrictStr, Field(min_length=1, max_length=1000, pattern=r"^\S(?:[\s\S]*\S)?$")]
Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
Region = Annotated[StrictStr, Field(pattern=r"^[A-Z]{2}$")]
Minor = Annotated[StrictInt, Field(ge=0, le=9223372036854775807)]
IntegerValue = Annotated[StrictInt, Field(ge=-9223372036854775808, le=9223372036854775807)]
ExactDecimal = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]


def source_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Expected a credential-free HTTP(S) source URL without fragment")
    return value


class CatalogRecord(Contract):
    id: UUID
    record_key: Annotated[Nonempty, Field(max_length=120)]
    synthetic: StrictBool = False

    @model_validator(mode="after")
    def isolation(self):
        if self.synthetic != self.record_key.startswith("TEST-"):
            raise ValueError("Synthetic records must use TEST-* keys; real records must not")
        return self

    @field_validator("*", mode="after")
    @classmethod
    def utc_times(cls, value):
        return value.astimezone(UTC) if isinstance(value, datetime) else value


class CatalogReviewed(CatalogRecord):
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    reviewer: Annotated[Nonempty, Field(max_length=120)] | None = None
    reviewed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def review_record(self):
        if self.review_status == "pending":
            if self.reviewer is not None or self.reviewed_at is not None:
                raise ValueError("Pending review cannot claim a reviewer or reviewed time")
        elif self.reviewer is None or self.reviewed_at is None:
            raise ValueError("A completed review requires reviewer and time")
        return self


class CatalogBrand(CatalogRecord):
    name: Annotated[Nonempty, Field(max_length=120)]
    normalized_name: Annotated[Nonempty, Field(max_length=120)]

    @model_validator(mode="after")
    def normalized(self):
        if self.normalized_name != self.name.strip().lower():
            raise ValueError("normalized_name must be lower-case trimmed source name")
        return self


class CatalogFamily(CatalogRecord):
    brand_id: UUID
    category: Category
    name: Annotated[Nonempty, Field(max_length=200)]


class CatalogSKU(CatalogRecord):
    family_id: UUID
    brand_id: UUID
    category: Category
    manufacturer_part_number: Annotated[Nonempty, Field(max_length=160)] | None = None
    normalized_part_number: Annotated[Nonempty, Field(max_length=160)] | None = None
    region: Region
    hardware_revision: Annotated[Nonempty, Field(max_length=80)] | None = None
    revision_status: Literal["unknown", "known", "not_applicable"] = "unknown"
    configuration_fingerprint: Digest | None = None
    identity_evidence_id: UUID | None = None
    identity_status: Literal["pending", "verified"] = "pending"
    status: Literal["active", "discontinued", "unknown"] = "unknown"

    @model_validator(mode="after")
    def exact_identity(self):
        expected = (
            self.manufacturer_part_number.strip().lower() if self.manufacturer_part_number else None
        )
        if self.normalized_part_number != expected:
            raise ValueError("Part number normalization mismatch")
        if self.revision_status == "known":
            if (
                self.hardware_revision is None
                or self.hardware_revision != self.hardware_revision.strip().lower()
            ):
                raise ValueError("Known revision requires its normalized exact value")
        elif self.hardware_revision is not None:
            raise ValueError("Unknown/not-applicable revision must be null")
        if self.identity_status == "verified" and (
            not self.identity_evidence_id
            or not self.normalized_part_number
            or self.revision_status == "unknown"
            or (self.category == "laptop" and not self.configuration_fingerprint)
        ):
            raise ValueError(
                "Verified identity requires evidence, part number, revision decision "
                "and laptop fingerprint"
            )
        return self


class CatalogAlias(CatalogRecord):
    sku_id: UUID
    alias: Annotated[Nonempty, Field(max_length=200)]
    normalized_alias: Annotated[Nonempty, Field(max_length=200)]
    locale: Annotated[Nonempty, Field(max_length=20)]

    @model_validator(mode="after")
    def normalized(self):
        if self.normalized_alias != self.alias.strip().lower():
            raise ValueError("Alias normalization mismatch")
        return self


class CatalogSource(CatalogRecord):
    name: Annotated[Nonempty, Field(max_length=200)]
    domain: Annotated[StrictStr, Field(max_length=253, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")]
    source_type: Literal["manufacturer", "merchant", "benchmark", "manual"]
    access_method: Literal["manual", "api", "web", "file"]
    permission_status: Literal["unknown", "allowed", "restricted", "denied"] = "unknown"
    permission_evidence: Nonempty | None = None
    terms_checked_at: AwareDatetime | None = None
    allowed_uses: list[
        Literal["internal_review", "public_display", "automated_fetch", "excerpt_storage"]
    ] = Field(default_factory=list, max_length=4)
    requests_per_minute: Annotated[StrictInt, Field(gt=0, le=2147483647)] | None = None

    @model_validator(mode="after")
    def permission(self):
        if len(self.allowed_uses) != len(set(self.allowed_uses)):
            raise ValueError("Duplicate allowed uses")
        if self.permission_status in {"unknown", "denied"}:
            if self.allowed_uses:
                raise ValueError("Unconfirmed permission grants no uses")
        elif not self.permission_evidence or not self.terms_checked_at or not self.allowed_uses:
            raise ValueError(
                "Allowed/restricted permission requires evidence, time and explicit uses"
            )
        return self


class CatalogDocument(CatalogRecord):
    source_id: UUID
    canonical_url: Annotated[StrictStr, Field(max_length=4000)]
    title: Annotated[Nonempty, Field(max_length=300)]
    content_sha256: Digest
    fetched_at: AwareDatetime
    published_at: AwareDatetime | None = None
    parser_version: Annotated[Nonempty, Field(max_length=80)]
    storage_key: (
        Annotated[StrictStr, Field(max_length=300, pattern=r"^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$")]
        | None
    ) = None
    _url = field_validator("canonical_url")(source_url)

    @model_validator(mode="after")
    def document_record(self):
        if self.published_at and self.published_at > self.fetched_at:
            raise ValueError("Publication cannot be later than fetch")
        if self.storage_key and any(part in {".", ".."} for part in self.storage_key.split("/")):
            raise ValueError("Storage key must be relative without path traversal")
        return self


class CatalogEvidence(CatalogReviewed):
    document_id: UUID
    locator_kind: Literal["page", "section", "selector", "json_pointer"]
    locator: Annotated[Nonempty, Field(max_length=500)]
    excerpt_sha256: Digest


class CatalogEvidenceScope(Contract):
    evidence_id: UUID
    sku_id: UUID
    synthetic: StrictBool


class CatalogAttribute(CatalogRecord):
    key: Annotated[StrictStr, Field(max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
    category: Category
    value_type: ValueType
    canonical_unit: Annotated[Nonempty, Field(max_length=24)]
    description: Annotated[Nonempty, Field(max_length=300)]


class CatalogFact(CatalogReviewed):
    sku_id: UUID
    attribute_id: UUID
    evidence_id: UUID
    category: Category
    value_type: ValueType
    unit: Annotated[Nonempty, Field(max_length=24)]
    value_text: Nonempty | None = None
    value_integer: IntegerValue | None = None
    value_decimal: ExactDecimal | None = None
    value_boolean: StrictBool | None = None
    missing_reason: Missing | None = None
    raw_value: Nonempty | None = None
    raw_unit: Annotated[Nonempty, Field(max_length=80)] | None = None
    conditions: dict[str, JsonValue] = Field(default_factory=dict)
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None

    @field_validator("value_decimal", mode="before")
    @classmethod
    def exact_decimal(cls, value):
        if value is not None and not isinstance(value, (str, Decimal)):
            raise ValueError("Decimal claims must use exact decimal strings, not floats")
        return value

    @model_validator(mode="after")
    def typed_claim(self):
        values = {
            key: getattr(self, f"value_{key}") for key in ("text", "integer", "decimal", "boolean")
        }
        present = [key for key, value in values.items() if value is not None]
        if self.missing_reason:
            if present:
                raise ValueError("Missing facts cannot contain an invented value")
        elif present != [self.value_type] or self.raw_value is None:
            raise ValueError("Fact requires one value matching its type and traceable raw value")
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("Invalid fact time interval")
        return self


class CatalogMerchant(CatalogRecord):
    name: Annotated[Nonempty, Field(max_length=200)]
    platform: Annotated[Nonempty, Field(max_length=100)]
    external_seller_id: Annotated[Nonempty, Field(max_length=160)]


class CatalogListing(CatalogRecord):
    merchant_id: UUID
    source_id: UUID
    external_listing_id: Annotated[Nonempty, Field(max_length=160)]
    listing_url: Annotated[StrictStr, Field(max_length=4000)]
    matched_sku_id: UUID | None = None
    match_evidence_id: UUID | None = None
    match_status: Literal["pending", "matched", "ambiguous", "rejected"] = "pending"
    _url = field_validator("listing_url")(source_url)

    @model_validator(mode="after")
    def match(self):
        if self.match_status == "matched":
            if self.matched_sku_id is None or self.match_evidence_id is None:
                raise ValueError("Matched listing requires exact SKU and match evidence")
        elif self.matched_sku_id is not None or self.match_evidence_id is not None:
            raise ValueError("Unresolved listings must not claim a SKU match")
        return self


class CatalogOffer(CatalogReviewed):
    listing_id: UUID
    sku_id: UUID
    evidence_id: UUID
    amount_minor: Minor | None = None
    amount_missing_reason: Missing | None = None
    shipping_minor: Minor | None = None
    tax_minor: Minor | None = None
    tax_included: StrictBool | None = None
    currency: Annotated[StrictStr, Field(pattern=r"^[A-Z]{3}$")]
    region: Region
    stock_status: Literal["in_stock", "out_of_stock", "preorder", "unknown"] = "unknown"
    condition: Literal["new", "used", "refurbished", "unknown"] = "unknown"
    eligibility_type: Literal["unconditional", "member", "coupon", "bundle", "unknown"] = "unknown"
    eligibility_details: Nonempty | None = None
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def pricing_context(self):
        if (self.amount_minor is None) != (self.amount_missing_reason is not None):
            raise ValueError("Unknown price needs a missing reason; known price must not have one")
        if self.tax_included is True and self.tax_minor not in {None, 0}:
            raise ValueError("Do not add tax twice to a tax-included price")
        if self.expires_at <= self.observed_at:
            raise ValueError("Invalid offer validity interval")
        if self.eligibility_type in {"member", "coupon", "bundle"} and not self.eligibility_details:
            raise ValueError("Conditional prices require explicit eligibility details")
        return self


RECORD_MODELS = (
    CatalogBrand,
    CatalogFamily,
    CatalogSKU,
    CatalogAlias,
    CatalogSource,
    CatalogDocument,
    CatalogEvidence,
    CatalogEvidenceScope,
    CatalogAttribute,
    CatalogFact,
    CatalogMerchant,
    CatalogListing,
    CatalogOffer,
)
