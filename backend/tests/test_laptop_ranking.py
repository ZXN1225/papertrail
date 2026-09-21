# ruff: noqa: E501
from uuid import uuid4

from app.recommendation.contracts import LaptopRankRequest
from app.recommendation.service import LaptopRanker


class Catalog:
    def __init__(self):
        self.version, self.a, self.b = uuid4(), uuid4(), uuid4()

    def list_products(self, **_):
        return {
            "items": [
                {
                    "id": self.a,
                    "brand": "TEST",
                    "family": "same",
                    "manufacturer_part_number": "TEST-A",
                },
                {
                    "id": self.b,
                    "brand": "TEST",
                    "family": "same",
                    "manufacturer_part_number": "TEST-B",
                },
            ],
            "data_version": self.version,
        }

    def product(self, sku):
        data = {
            self.a: [("weight_g", 1200), ("memory_gib", 16), ("battery_life_hours", 10)],
            self.b: [("weight_g", 2000), ("memory_gib", 8)],
        }[sku]
        return {"facts": [{"key": key, "value": value, "conditions": {}} for key, value in data]}


def test_exact_sku_hard_filters_do_not_leak_family_facts(monkeypatch):
    catalog = Catalog()
    monkeypatch.setattr(
        "app.recommendation.service.ManualOfferProvider.offers",
        lambda _, sku, region: [
            {
                "id": uuid4(),
                "amount_minor": 100000,
                "shipping_minor": 0,
                "tax_minor": 0,
                "tax_included": True,
            }
        ],
    )
    result = LaptopRanker(catalog).rank(
        LaptopRankRequest(budget_minor=200000, min_memory_gib=16, max_weight_g=1500)
    )
    assert result["status"] == "ok" and [item["sku_id"] for item in result["candidates"]] == [
        catalog.a
    ]


def test_unknown_published_catalog_returns_honest_empty():
    class Empty:
        def list_products(self, **_):
            return {"items": [], "data_version": None}

    result = LaptopRanker(Empty()).rank(LaptopRankRequest(budget_minor=1))
    assert result["status"] == "no_candidates" and result["data_version"] is None


def test_incomplete_offer_total_is_not_treated_as_budget_pass(monkeypatch):
    catalog = Catalog()
    monkeypatch.setattr(
        "app.recommendation.service.ManualOfferProvider.offers",
        lambda _, sku, region: [
            {
                "id": uuid4(),
                "amount_minor": 100000,
                "shipping_minor": None,
                "tax_minor": 0,
                "tax_included": True,
            }
        ],
    )
    result = LaptopRanker(catalog).rank(LaptopRankRequest(budget_minor=200000))
    assert result["status"] == "no_candidates"
    assert result["missing_data"] == ["complete_current_offer"]
