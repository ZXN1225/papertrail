# ruff: noqa: E501
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.compatibility.contracts import CompatibilityRequest
from app.compatibility.service import CompatibilityService


class Catalog:
    def __init__(self, products):
        self.products = products
        self.clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)

    def product(self, sku_id):
        return self.products[str(sku_id)]


def fact(key, value, conditions=None):
    return {"id": uuid4(), "key": key, "value": value, "conditions": conditions or {}}


def fixture():
    version, cpu, board, memory = uuid4(), uuid4(), uuid4(), uuid4()
    products = {
        str(cpu): {
            "id": cpu,
            "category": "cpu",
            "data_version": version,
            "facts": [
                fact("socket", "AM5"),
                fact("supported_memory_type", "DDR5"),
                fact("max_memory_gib", 192),
            ],
        },
        str(board): {
            "id": board,
            "category": "motherboard",
            "hardware_revision": "rev-1",
            "data_version": version,
            "facts": [
                fact("socket", "AM5"),
                fact("memory_type", "DDR5"),
                fact("memory_slots", 4),
                fact("max_memory_gib", 128),
                fact(
                    "cpu_support_entry",
                    str(cpu),
                    {"board_revision": "rev-1", "minimum_bios": "2.10"},
                ),
            ],
        },
        str(memory): {
            "id": memory,
            "category": "memory",
            "data_version": version,
            "facts": [
                fact("memory_type", "DDR5"),
                fact("kit_modules", 2),
                fact("kit_capacity_gib", 32),
            ],
        },
    }
    return products, cpu, board, memory


def check(products, cpu, board, memory, **extra):
    return CompatibilityService(Catalog(products)).check(
        CompatibilityRequest(
            items=[
                {"slot": "cpu", "sku_id": cpu},
                {"slot": "motherboard", "sku_id": board},
                {"slot": "memory", "sku_id": memory, "quantity": 2},
            ],
            **extra,
        )
    )


def test_all_core_rules_pass_but_remaining_rules_require_verification():
    products, cpu, board, memory = fixture()
    report = check(products, cpu, board, memory, bios_version="2.10")
    assert [item["status"] for item in report["results"]] == ["pass", "pass", "pass"]
    assert report["status"] == "needs_verification" and "C012" in report["unexecuted_rule_ids"]


@pytest.mark.parametrize(
    "key,value,rule",
    [("socket", "LGA1700", "C001"), ("memory_type", "DDR4", "C003"), ("memory_slots", 1, "C003")],
)
def test_explicit_socket_generation_and_kit_conflicts_fail(key, value, rule):
    products, cpu, board, memory = fixture()
    target = products[str(board)] if key != "memory_type" else products[str(memory)]
    next(item for item in target["facts"] if item["key"] == key)["value"] = value
    report = check(products, cpu, board, memory, bios_version="2.10")
    assert next(item for item in report["results"] if item["rule_id"] == rule)["status"] == "fail"
    assert report["status"] == "incompatible"


def test_same_socket_does_not_bypass_bios_unknown_or_too_old():
    products, cpu, board, memory = fixture()
    unknown = check(products, cpu, board, memory)
    old = check(products, cpu, board, memory, bios_version="2.9")
    assert unknown["results"][1]["status"] == "unknown"
    assert old["results"][1]["status"] == "fail" and old["status"] == "incompatible"
