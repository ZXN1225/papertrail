"""C001--C003 are deterministic and intentionally reject missing evidence."""
# ruff: noqa: E501

import re

from app.compatibility.contracts import RuleResult
from app.profiles.service import DomainError

RULE_VERSION = "compat-v1"
UNEXECUTED = ["C004", "C005", "C006", "C007", "C008", "C009", "C010", "C011", "C012"]


def _normalized(value):
    return value.strip().casefold() if isinstance(value, str) else None


def _bios(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){0,3}", value):
        return None
    return tuple(int(part) for part in value.split("."))


def _at_least(current, required):
    width = max(len(current), len(required))
    return current + (0,) * (width - len(current)) >= required + (0,) * (width - len(required))


class CompatibilityService:
    def __init__(self, catalog):
        self.catalog = catalog

    @staticmethod
    def _facts(product):
        grouped = {}
        for fact in product["facts"]:
            grouped.setdefault(fact["key"], []).append(fact)
        return grouped

    @staticmethod
    def _unconditional(facts, key):
        candidates = [fact for fact in facts.get(key, []) if not fact["conditions"]]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _result(rule_id, status, message, facts=(), **details):
        return RuleResult(
            rule_id=rule_id,
            status=status,
            message=message,
            fact_ids=[fact["id"] for fact in facts if fact],
            details=details,
        ).model_dump()

    def _load(self, request):
        products, versions = {}, set()
        for item in request.items:
            product = self.catalog.product(item.sku_id)
            if product["category"] != item.slot:
                raise DomainError(
                    422, "COMPONENT_CATEGORY_MISMATCH", "零件槽位与已发布 SKU 类别不一致。"
                )
            products[item.slot] = {"item": item, "product": product, "facts": self._facts(product)}
            versions.add(product["data_version"])
        if len(versions) != 1:
            raise DomainError(
                503, "CATALOG_VERSION_CHANGED", "目录版本已更新，请重新执行兼容性检查。"
            )
        return products, versions.pop()

    def _c001(self, products):
        cpu, board = products.get("cpu"), products.get("motherboard")
        if not cpu or not board:
            return self._result(
                "C001",
                "unknown",
                "缺少 CPU 或主板，无法检查 socket。",
                missing_slots=["cpu", "motherboard"],
            )
        cpu_socket = self._unconditional(cpu["facts"], "socket")
        board_socket = self._unconditional(board["facts"], "socket")
        if not cpu_socket or not board_socket:
            return self._result(
                "C001",
                "unknown",
                "CPU 或主板缺少唯一且无条件的 socket 事实。",
                cpu_socket=bool(cpu_socket),
                motherboard_socket=bool(board_socket),
            )
        matched = _normalized(cpu_socket["value"]) == _normalized(board_socket["value"])
        return self._result(
            "C001",
            "pass" if matched else "fail",
            "CPU 与主板 socket 一致。" if matched else "CPU 与主板 socket 不一致。",
            [cpu_socket, board_socket],
            cpu_socket=cpu_socket["value"],
            motherboard_socket=board_socket["value"],
        )

    def _c002(self, products, bios_version):
        cpu, board = products.get("cpu"), products.get("motherboard")
        if not cpu or not board:
            return self._result("C002", "unknown", "缺少 CPU 或主板，无法检查 CPU 支持表与 BIOS。")
        revision = board["product"]["hardware_revision"]
        entries = []
        for fact in board["facts"].get("cpu_support_entry", []):
            conditions = fact["conditions"]
            if (
                str(fact["value"]) == str(cpu["product"]["id"])
                and conditions.get("board_revision") == revision
                and isinstance(conditions.get("minimum_bios"), str)
            ):
                entries.append(fact)
        if len(entries) != 1:
            return self._result(
                "C002",
                "unknown",
                "缺少该 CPU 与主板精确 revision 对应的唯一支持条目。",
                board_revision=revision,
            )
        entry = entries[0]
        required = entry["conditions"]["minimum_bios"]
        current, minimum = _bios(bios_version), _bios(required)
        if current is None or minimum is None:
            return self._result(
                "C002",
                "unknown",
                "当前 BIOS 或最低 BIOS 版本无法按受支持格式比较。",
                [entry],
                current_bios=bios_version,
                minimum_bios=required,
            )
        passed = _at_least(current, minimum)
        return self._result(
            "C002",
            "pass" if passed else "fail",
            "当前 BIOS 满足该 CPU 的最低要求。" if passed else "当前 BIOS 低于该 CPU 的最低要求。",
            [entry],
            current_bios=bios_version,
            minimum_bios=required,
            board_revision=revision,
        )

    def _c003(self, products):
        cpu, board, memory = (
            products.get("cpu"),
            products.get("motherboard"),
            products.get("memory"),
        )
        if not cpu or not board or not memory:
            return self._result("C003", "unknown", "缺少 CPU、主板或内存，无法检查内存兼容性。")
        needed = {
            "cpu_memory_type": self._unconditional(cpu["facts"], "supported_memory_type"),
            "cpu_max_memory_gib": self._unconditional(cpu["facts"], "max_memory_gib"),
            "motherboard_memory_type": self._unconditional(board["facts"], "memory_type"),
            "motherboard_memory_slots": self._unconditional(board["facts"], "memory_slots"),
            "motherboard_max_memory_gib": self._unconditional(board["facts"], "max_memory_gib"),
            "memory_type": self._unconditional(memory["facts"], "memory_type"),
            "kit_modules": self._unconditional(memory["facts"], "kit_modules"),
            "kit_capacity_gib": self._unconditional(memory["facts"], "kit_capacity_gib"),
        }
        missing = [key for key, fact in needed.items() if fact is None]
        if missing:
            return self._result(
                "C003", "unknown", "缺少唯一且无条件的内存规格事实。", missing_fields=missing
            )
        values = {key: fact["value"] for key, fact in needed.items()}
        if not all(
            isinstance(values[key], int)
            for key in values
            if key not in {"cpu_memory_type", "motherboard_memory_type", "memory_type"}
        ):
            return self._result(
                "C003", "unknown", "内存容量、插槽数或套装条数不是整数事实。", list(needed.values())
            )
        memory_types = {
            _normalized(values[key])
            for key in ("cpu_memory_type", "motherboard_memory_type", "memory_type")
        }
        kits = memory["item"].quantity
        total_modules = values["kit_modules"] * kits
        total_capacity = values["kit_capacity_gib"] * kits
        reasons = []
        if None in memory_types or len(memory_types) != 1:
            reasons.append("MEMORY_GENERATION_MISMATCH")
        if total_modules > values["motherboard_memory_slots"]:
            reasons.append("MEMORY_SLOTS_EXCEEDED")
        if total_capacity > values["cpu_max_memory_gib"]:
            reasons.append("CPU_MEMORY_CAPACITY_EXCEEDED")
        if total_capacity > values["motherboard_max_memory_gib"]:
            reasons.append("MOTHERBOARD_MEMORY_CAPACITY_EXCEEDED")
        return self._result(
            "C003",
            "fail" if reasons else "pass",
            "内存代际、条数和容量满足当前事实。"
            if not reasons
            else "内存代际、条数或容量不满足当前事实。",
            list(needed.values()),
            reasons=reasons,
            kits=kits,
            total_modules=total_modules,
            total_capacity_gib=total_capacity,
        )

    def check(self, request):
        products, version = self._load(request)
        results = [
            self._c001(products),
            self._c002(products, request.bios_version),
            self._c003(products),
        ]
        return {
            "rule_version": RULE_VERSION,
            "status": "incompatible"
            if any(result["status"] == "fail" for result in results)
            else "needs_verification",
            "results": results,
            "unexecuted_rule_ids": UNEXECUTED,
            "data_version": version,
            "generated_at": self.catalog.clock(),
        }
