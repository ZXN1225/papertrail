# ruff: noqa: E501
from datetime import UTC, datetime
from uuid import uuid4

from app.recommendation.contracts import PcSolveRequest
from app.recommendation.pc_solver import PcSolver


def fact(key, value, conditions=None):
    return {"id": uuid4(), "key": key, "value": value, "conditions": conditions or {}}


class Catalog:
    def __init__(self):
        self.version = uuid4()
        self.cpu_a, self.cpu_b, self.board, self.memory, self.storage, self.psu, self.case = [
            uuid4() for _ in range(7)
        ]
        self.clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)
        self.products = {
            self.cpu_a: self._product(
                "cpu",
                [
                    fact("socket", "AM5"),
                    fact("supported_memory_type", "DDR5"),
                    fact("max_memory_gib", 192),
                    fact("max_power_w", 80),
                    fact("includes_cooler", True),
                    fact("integrated_graphics", True),
                    fact("application_performance", 50),
                ],
            ),
            self.cpu_b: self._product(
                "cpu",
                [
                    fact("socket", "AM5"),
                    fact("supported_memory_type", "DDR5"),
                    fact("max_memory_gib", 192),
                    fact("max_power_w", 80),
                    fact("includes_cooler", True),
                    fact("integrated_graphics", True),
                    fact("application_performance", 100),
                ],
            ),
            self.board: self._product(
                "motherboard",
                [
                    fact("socket", "AM5"),
                    fact("memory_type", "DDR5"),
                    fact("memory_slots", 4),
                    fact("max_memory_gib", 128),
                    fact("form_factor", "ATX"),
                    fact("supported_storage_interfaces", "NVME"),
                    fact("video_output_count", 1),
                    fact(
                        "cpu_support_entry",
                        str(self.cpu_a),
                        {"board_revision": "r1", "minimum_bios": "1.0"},
                    ),
                    fact(
                        "cpu_support_entry",
                        str(self.cpu_b),
                        {"board_revision": "r1", "minimum_bios": "1.0"},
                    ),
                ],
                hardware_revision="r1",
            ),
            self.memory: self._product(
                "memory",
                [fact("memory_type", "DDR5"), fact("kit_modules", 2), fact("kit_capacity_gib", 32)],
            ),
            self.storage: self._product("storage", [fact("interface", "NVME")]),
            self.psu: self._product(
                "psu", [fact("rated_power_w", 500), fact("form_factor", "ATX")]
            ),
            self.case: self._product(
                "case",
                [fact("supported_form_factors", "ATX"), fact("supported_psu_form_factors", "ATX")],
            ),
        }
        for sku, product in self.products.items():
            product["id"] = sku
        self.prices = {
            self.cpu_a: 10000,
            self.cpu_b: 20000,
            self.board: 15000,
            self.memory: 10000,
            self.storage: 10000,
            self.psu: 10000,
            self.case: 10000,
        }

    def _product(self, category, facts, hardware_revision=None):
        return {
            "id": uuid4(),
            "category": category,
            "data_version": self.version,
            "hardware_revision": hardware_revision,
            "facts": facts,
        }

    def list_products(self, category, **_):
        items = [
            {"id": sku, "brand": "TEST", "category": product["category"]}
            for sku, product in self.products.items()
            if product["category"] == category
        ]
        return {"items": items, "data_version": self.version}

    def product(self, sku_id):
        return self.products[sku_id]

    def current_offers(self, sku_id, region):
        return [
            {
                "id": uuid4(),
                "amount_minor": self.prices[sku_id],
                "shipping_minor": 0,
                "tax_minor": 0,
                "tax_included": True,
            }
        ]


def test_bounded_solver_matches_small_pool_and_enforces_one_minor_budget_boundary():
    catalog = Catalog()
    exact_total = sum(catalog.prices.values()) - catalog.prices[catalog.cpu_b]
    accepted = PcSolver(catalog).solve(PcSolveRequest(budget_minor=exact_total, bios_version="1.0"))
    rejected = PcSolver(catalog).solve(
        PcSolveRequest(budget_minor=exact_total - 1, bios_version="1.0")
    )
    assert accepted["status"] == "ok"
    assert accepted["candidates"][0]["total_minor"] == exact_total
    assert accepted["optimality_proven"] is False and accepted["explored_count"] > 0
    assert rejected["status"] == "no_candidates" and rejected["pruned_count"] > 0


def test_existing_locked_item_is_retained_and_excluded_from_purchase_budget():
    catalog = Catalog()
    result = PcSolver(catalog).solve(
        PcSolveRequest(
            budget_minor=55000,
            bios_version="1.0",
            existing_items=[{"slot": "cpu", "sku_id": catalog.cpu_a}],
        )
    )
    cpu = next(item for item in result["candidates"][0]["items"] if item["slot"] == "cpu")
    assert cpu["owned"] is True and cpu["total_minor"] is None


def test_time_limit_is_distinct_from_no_solution():
    catalog = Catalog()
    solver = PcSolver(catalog)
    solver.TIME_LIMIT_SECONDS = 0
    result = solver.solve(PcSolveRequest(budget_minor=100000, bios_version="1.0"))
    assert result["status"] == "incomplete_search" and result["search_status"] == "time_limit"
