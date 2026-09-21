"""Public read contracts. These expose only an already published version."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from app.catalog.contracts import Category, Missing, Region
from app.common.contracts import Contract

PageSize = Annotated[StrictInt, Field(ge=1, le=100)]
Minor = Annotated[StrictInt, Field(ge=0, le=9223372036854775807)]


class CatalogPage(Contract):
    items: list["ProductSummary"]
    next_cursor: str | None = None
    data_version: UUID | None = None
    generated_at: AwareDatetime
    empty_reason: Literal["no_published_catalog"] | None = None


class ProductSummary(Contract):
    id: UUID
    record_key: str
    category: Category
    region: Region
    brand: str
    family: str
    manufacturer_part_number: str | None
    status: Literal["active", "discontinued", "unknown"]
    data_version: UUID
    missing_key_facts: StrictBool


class SourceReference(Contract):
    source_name: str
    source_domain: str
    document_title: str
    canonical_url: str
    document_hash: str
    fetched_at: AwareDatetime
    locator_kind: Literal["page", "section", "selector", "json_pointer"]
    locator: str
    excerpt_hash: str


class FactView(Contract):
    id: UUID
    key: str
    description: str
    value_type: Literal["text", "integer", "decimal", "boolean"]
    value: str | StrictInt | StrictBool | None
    unit: str
    raw_value: str | None
    raw_unit: str | None
    missing_reason: Missing | None
    conditions: dict
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None
    evidence: SourceReference


class ProductDetail(ProductSummary):
    identity_status: Literal["pending", "verified"]
    revision_status: Literal["unknown", "known", "not_applicable"]
    hardware_revision: str | None
    configuration_fingerprint: str | None
    aliases: list[str]
    facts: list[FactView]


class OfferView(Contract):
    id: UUID
    sku_id: UUID
    merchant_name: str
    platform: str
    listing_url: str
    amount_minor: Minor | None
    amount_missing_reason: Missing | None
    shipping_minor: Minor | None
    tax_minor: Minor | None
    tax_included: StrictBool | None
    currency: Literal["CNY"]
    region: Region
    stock_status: Literal["in_stock", "out_of_stock", "preorder", "unknown"]
    condition: Literal["new", "used", "refurbished", "unknown"]
    eligibility_type: Literal["unconditional", "member", "coupon", "bundle", "unknown"]
    eligibility_details: str | None
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    freshness: Literal["current", "historical"]
    evidence: SourceReference
    data_version: UUID


class OfferPage(Contract):
    items: list[OfferView]
    data_version: UUID | None = None
    generated_at: AwareDatetime
    empty_reason: Literal["no_published_catalog", "no_matching_offers"] | None = None


class PriceItemInput(Contract):
    sku_id: UUID
    quantity: Annotated[StrictInt, Field(ge=1, le=99)] = 1
    offer_id: UUID | None = None


class PriceRequest(Contract):
    region: Region = "CN"
    budget_minor: Minor | None = None
    items: Annotated[list[PriceItemInput], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def distinct_skus(self):
        if len({item.sku_id for item in self.items}) != len(self.items):
            raise ValueError("Each SKU appears only once; combine its quantity")
        return self


class PricedLine(Contract):
    sku_id: UUID
    quantity: StrictInt
    offer_id: UUID | None
    amount_minor: Minor | None
    shipping_minor: Minor | None
    tax_minor: Minor | None
    tax_included: StrictBool | None
    known_total_minor: Minor
    unpriced_reasons: list[
        Literal["NO_CURRENT_OFFER", "PRICE_UNKNOWN", "SHIPPING_UNKNOWN", "TAX_UNKNOWN"]
    ]
    expires_at: AwareDatetime | None


class PriceQuote(Contract):
    data_version: UUID | None
    lines: list[PricedLine]
    known_subtotal_minor: Minor
    total_minor: Minor | None
    price_complete: StrictBool
    budget_minor: Minor | None
    budget_satisfied: StrictBool | None
    expires_at: AwareDatetime | None
    generated_at: AwareDatetime
