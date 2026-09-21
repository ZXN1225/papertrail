"""Bounded deterministic PC search over exact published SKUs."""

from __future__ import annotations

from time import monotonic

from app.catalog.read_service import ManualOfferProvider
from app.compatibility.contracts import CompatibilityRequest
from app.compatibility.service import CompatibilityService
from app.profiles.service import DomainError


class PcSolver:
    """A deliberately bounded beam search; it never claims global optimality."""

    SCORE_VERSION = "pc-score-v1"
    MAX_PER_SLOT = 20
    BEAM_WIDTH = 100
    TIME_LIMIT_SECONDS = 5.0
    REQUIRED = ("cpu", "motherboard", "memory", "storage", "psu", "case")

    def __init__(self, catalog, clock=monotonic):
        self.catalog = catalog
        self.clock = clock
        self.compatibility = CompatibilityService(catalog)

    @staticmethod
    def _fact(product, key):
        facts = [fact for fact in product["facts"] if fact["key"] == key and not fact["conditions"]]
        return facts[0]["value"] if len(facts) == 1 else None

    def _offer(self, sku_id, region):
        offers = ManualOfferProvider(self.catalog).offers(sku_id, region)
        for offer in offers:
            if (
                offer["amount_minor"] is not None
                and offer["shipping_minor"] is not None
                and (offer["tax_included"] is True or offer["tax_minor"] is not None)
            ):
                return {
                    "id": offer["id"],
                    "total_minor": offer["amount_minor"]
                    + offer["shipping_minor"]
                    + (0 if offer["tax_included"] else offer["tax_minor"]),
                }
        return None

    def _pool(self, slot, request, fixed):
        if slot in fixed:
            product = self.catalog.product(fixed[slot]["sku_id"])
            if product["category"] != slot:
                raise DomainError(422, "COMPONENT_CATEGORY_MISMATCH", "锁定零件与槽位类别不一致。")
            if fixed[slot]["owned"]:
                return [{"slot": slot, "product": product, "offer": None, "owned": True}]
            offer = self._offer(product["id"], request.region)
            return (
                []
                if offer is None
                else [{"slot": slot, "product": product, "offer": offer, "owned": False}]
            )
        page = self.catalog.list_products(category=slot, region=request.region, limit=100)
        pool = []
        excluded = {brand.casefold() for brand in request.excluded_brands}
        for summary in page["items"]:
            if summary["brand"].casefold() in excluded:
                continue
            product = self.catalog.product(summary["id"])
            offer = self._offer(product["id"], request.region)
            if offer:
                pool.append({"slot": slot, "product": product, "offer": offer, "owned": False})
        pool.sort(key=lambda item: (item["offer"]["total_minor"], str(item["product"]["id"])))
        return pool[: self.MAX_PER_SLOT]

    @staticmethod
    def _candidate_items(state):
        return [
            {
                "slot": item["slot"],
                "sku_id": item["product"]["id"],
                "offer_id": item["offer"]["id"] if item["offer"] else None,
                "owned": item["owned"],
                "total_minor": item["offer"]["total_minor"] if item["offer"] else None,
            }
            for item in state
        ]

    @staticmethod
    def _score(state, budget):
        total = sum(item["offer"]["total_minor"] for item in state if item["offer"])
        performance = [
            PcSolver._fact(item["product"], "application_performance")
            for item in state
            if item["slot"] in {"cpu", "gpu"}
        ]
        known = [value for value in performance if isinstance(value, int)]
        performance_score = min(1.0, sum(known) / (200 * max(1, len(performance))))
        coverage = 0.3 + (0.7 if len(known) == len(performance) and performance else 0.0)
        score = 100 * (0.7 * performance_score + 0.3 * max(0, 1 - total / budget))
        return round(score, 2), round(coverage, 2), total

    def solve(self, request):
        page = self.catalog.list_products(category="cpu", region=request.region, limit=1)
        version = page["data_version"]
        if version is None:
            return self._empty("no_published_catalog", "no_published_catalog", None)

        fixed = {
            item.slot: {"sku_id": item.sku_id, "owned": False} for item in request.locked_items
        }
        fixed.update(
            {item.slot: {"sku_id": item.sku_id, "owned": True} for item in request.existing_items}
        )
        slots = list(self.REQUIRED)
        if request.require_gpu or "gpu" in fixed:
            slots.insert(2, "gpu")
        pools = {slot: self._pool(slot, request, fixed) for slot in slots}
        missing = sorted(slot for slot, pool in pools.items() if not pool)
        if missing:
            return self._empty("complete", "no_candidates", version, missing_data=missing)

        minimum = {
            slot: min(item["offer"]["total_minor"] if item["offer"] else 0 for item in pool)
            for slot, pool in pools.items()
        }
        started, explored, pruned, timed_out = self.clock(), 0, 0, False
        states = [([], 0)]
        for position, slot in enumerate(slots):
            next_states = []
            remaining = slots[position + 1 :]
            floor = sum(minimum[name] for name in remaining)
            for state, subtotal in states:
                for item in pools[slot]:
                    if self.clock() - started >= self.TIME_LIMIT_SECONDS:
                        timed_out = True
                        break
                    explored += 1
                    total = subtotal + (item["offer"]["total_minor"] if item["offer"] else 0)
                    if total + floor > request.budget_minor:
                        pruned += 1
                        continue
                    next_states.append((state + [item], total))
                if timed_out:
                    break
            next_states.sort(
                key=lambda pair: (pair[1], tuple(str(x["product"]["id"]) for x in pair[0]))
            )
            if len(next_states) > self.BEAM_WIDTH:
                pruned += len(next_states) - self.BEAM_WIDTH
                next_states = next_states[: self.BEAM_WIDTH]
            states = next_states
            if timed_out or not states:
                break

        candidates = []
        if not timed_out:
            for state, _ in states:
                cpu = next(item for item in state if item["slot"] == "cpu")
                bundled = self._fact(cpu["product"], "includes_cooler")
                final_states = [state]
                if bundled is False and "cooler" not in fixed:
                    cooler_pool = self._pool("cooler", request, fixed)
                    final_states = [state + [cooler] for cooler in cooler_pool]
                for final in final_states:
                    score, coverage, total = self._score(final, request.budget_minor)
                    if total > request.budget_minor:
                        pruned += 1
                        continue
                    report = self.compatibility.check(
                        CompatibilityRequest(
                            items=[
                                {"slot": item["slot"], "sku_id": item["product"]["id"]}
                                for item in final
                            ],
                            bios_version=request.bios_version,
                            hard_requirements=request.hard_requirements,
                        )
                    )
                    if report["status"] != "validated":
                        pruned += 1
                        continue
                    candidates.append(
                        {
                            "items": self._candidate_items(final),
                            "total_minor": total,
                            "score": score,
                            "evidence_coverage": coverage,
                            "compatibility": report,
                            "data_version": version,
                        }
                    )
        candidates.sort(
            key=lambda item: (
                -item["score"],
                -item["evidence_coverage"],
                item["total_minor"],
                str(item["items"]),
            )
        )
        search_status = "time_limit" if timed_out else "complete"
        status = "incomplete_search" if timed_out else "ok" if candidates else "no_candidates"
        return {
            "score_version": self.SCORE_VERSION,
            "status": status,
            "search_status": search_status,
            "candidates": candidates[:3],
            "explored_count": explored,
            "pruned_count": pruned,
            "candidate_pool_version": version,
            "optimality_proven": False,
            "blocking_constraints": [] if candidates else ["budget_or_compatibility"],
            "missing_data": [],
            "relaxation_options": ["increase_budget", "remove_locked_item"]
            if not candidates
            else [],
        }

    def _empty(self, search_status, status, version, missing_data=None):
        return {
            "score_version": self.SCORE_VERSION,
            "status": status,
            "search_status": search_status,
            "candidates": [],
            "explored_count": 0,
            "pruned_count": 0,
            "candidate_pool_version": version,
            "optimality_proven": False,
            "blocking_constraints": ["no_published_catalog"] if version is None else [],
            "missing_data": missing_data or [],
            "relaxation_options": [],
        }
