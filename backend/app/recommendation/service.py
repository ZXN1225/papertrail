"""Exact-SKU laptop filtering and fixed-anchor scoring."""
# ruff: noqa: E501, E701, E702

from app.catalog.read_service import ManualOfferProvider


class LaptopRanker:
    WEIGHTS = {
        "weight_g": 0.25,
        "battery_life_hours": 0.25,
        "screen_quality": 0.20,
        "price": 0.20,
        "application_performance": 0.10,
    }

    def __init__(self, catalog):
        self.catalog = catalog

    @staticmethod
    def _fact(detail, key):
        facts = [fact for fact in detail["facts"] if fact["key"] == key and not fact["conditions"]]
        return facts[0]["value"] if len(facts) == 1 else None

    @staticmethod
    def _utility(key, value, budget):
        if key == "weight_g":
            return max(0, min(1, (2500 - value) / 1000))
        if key == "battery_life_hours":
            return max(0, min(1, value / 12))
        if key == "screen_quality":
            return max(0, min(1, value / 100))
        if key == "application_performance":
            return max(0, min(1, value / 100))
        return max(0, min(1, 1 - value / budget))

    def rank(self, request):
        page = self.catalog.list_products(category="laptop", region=request.region, limit=100)
        if page["data_version"] is None:
            return {
                "status": "no_candidates",
                "candidates": [],
                "blocking_constraints": ["no_published_catalog"],
                "missing_data": [],
                "data_version": None,
            }
        candidates, missing = [], set()
        provider = ManualOfferProvider(self.catalog)
        excluded = {brand.casefold() for brand in request.excluded_brands}
        for summary in page["items"]:
            if summary["brand"].casefold() in excluded:
                continue
            detail = self.catalog.product(summary["id"])
            weight, memory = self._fact(detail, "weight_g"), self._fact(detail, "memory_gib")
            if request.max_weight_g is not None and (
                not isinstance(weight, int) or weight > request.max_weight_g
            ):
                missing.add("weight_g")
                continue
            if request.min_memory_gib is not None and (
                not isinstance(memory, int) or memory < request.min_memory_gib
            ):
                missing.add("memory_gib")
                continue
            offers = provider.offers(summary["id"], request.region)
            if not offers:
                missing.add("current_offer")
                continue
            offer = offers[0]
            if (
                offer["amount_minor"] is None
                or offer["shipping_minor"] is None
                or (offer["tax_included"] is not True and offer["tax_minor"] is None)
            ):
                missing.add("complete_current_offer")
                continue
            total = (
                offer["amount_minor"]
                + offer["shipping_minor"]
                + (0 if offer["tax_included"] else offer["tax_minor"])
            )
            if total > request.budget_minor:
                continue
            values = {
                key: self._fact(detail, key)
                for key in (
                    "weight_g",
                    "battery_life_hours",
                    "screen_quality",
                    "application_performance",
                )
            }
            values["price"] = total
            soft_missing = [
                key
                for key in ("battery_life_hours", "screen_quality", "application_performance")
                if not isinstance(values[key], int)
            ]
            lower = (
                sum(
                    self.WEIGHTS[key] * self._utility(key, value, request.budget_minor)
                    for key, value in values.items()
                    if isinstance(value, int)
                )
                * 100
            )
            upper = lower + sum(self.WEIGHTS[key] for key in soft_missing) * 100
            coverage = sum(
                self.WEIGHTS[key] for key, value in values.items() if isinstance(value, int)
            )
            candidates.append(
                {
                    "sku_id": summary["id"],
                    "brand": summary["brand"],
                    "family": summary["family"],
                    "manufacturer_part_number": summary["manufacturer_part_number"],
                    "offer_id": offer["id"],
                    "total_minor": total,
                    "score_lower": round(lower, 2),
                    "score_upper": round(upper, 2),
                    "evidence_coverage": round(coverage, 2),
                    "missing_score_fields": soft_missing,
                    "data_version": page["data_version"],
                }
            )
        candidates.sort(
            key=lambda item: (
                -item["score_lower"],
                -item["evidence_coverage"],
                item["total_minor"],
                str(item["sku_id"]),
            )
        )
        return {
            "status": "ok" if candidates else "no_candidates",
            "candidates": candidates[:3],
            "blocking_constraints": [] if candidates else ["budget_or_hard_filters"],
            "missing_data": sorted(missing),
            "data_version": page["data_version"],
        }
