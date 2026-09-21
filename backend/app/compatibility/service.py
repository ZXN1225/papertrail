"""C001--C003 are deterministic and intentionally reject missing evidence."""
# ruff: noqa: E501

import re
from math import ceil

from app.compatibility.contracts import RuleResult
from app.profiles.service import DomainError

RULE_VERSION = "compat-v1"
UNEXECUTED = []


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
    def _result(rule_id, status, message, facts=(), blocking=True, **details):
        return RuleResult(
            rule_id=rule_id,
            status=status,
            message=message,
            blocking=blocking,
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

    def _c_simple(self, rule_id, products, required, comparator):
        selected = [products.get(slot) for slot in required]
        if any(item is None for item in selected):
            return self._result(rule_id, "unknown", "缺少该规则所需零件。", missing_slots=required)
        facts = [self._unconditional(item["facts"], key) for item, key in comparator["facts"]]
        if any(fact is None for fact in facts):
            return self._result(
                rule_id,
                "unknown",
                "缺少该规则所需的已选择规格事实。",
                missing_fields=[key for _, key in comparator["facts"]],
            )
        values = [fact["value"] for fact in facts]
        passed, details = comparator["check"](*values)
        return self._result(
            rule_id,
            "pass" if passed else "fail",
            comparator["pass"] if passed else comparator["fail"],
            facts,
            **details,
        )

    def _additional(self, products):
        def text_set(value):
            return {_normalized(v) for v in value.split(",")} if isinstance(value, str) else set()

        rules = []
        rules.append(
            self._c_simple(
                "C004",
                products,
                ["motherboard", "case"],
                {
                    "facts": [
                        (products.get("motherboard"), "form_factor"),
                        (products.get("case"), "supported_form_factors"),
                    ],
                    "check": lambda board, case: (
                        _normalized(board) in text_set(case),
                        {"board_form_factor": board, "case_supported": case},
                    ),
                    "pass": "主板外形受机箱支持。",
                    "fail": "机箱不支持主板外形。",
                },
            )
        )
        bundled = (
            self._unconditional(products["cpu"]["facts"], "includes_cooler")
            if products.get("cpu")
            else None
        )
        if "cooler" not in products and bundled and bundled["value"] is True:
            rules.append(self._result("C006", "pass", "CPU 包装含散热器。", [bundled]))
        else:
            rules.append(
                self._c_simple(
                    "C006",
                    products,
                    ["cpu", "cooler"],
                    {
                        "facts": [
                            (products.get("cpu"), "socket"),
                            (products.get("cooler"), "supported_sockets"),
                        ],
                        "check": lambda socket, cooler: (
                            _normalized(socket) in text_set(cooler),
                            {"socket": socket, "cooler_supported": cooler},
                        ),
                        "pass": "散热器扣具支持 CPU socket。",
                        "fail": "散热器扣具不支持 CPU socket。",
                    },
                )
            )
        rules.append(
            self._c_simple(
                "C007",
                products,
                ["psu", "case"],
                {
                    "facts": [
                        (products.get("psu"), "form_factor"),
                        (products.get("case"), "supported_psu_form_factors"),
                    ],
                    "check": lambda psu, case: (
                        _normalized(psu) in text_set(case),
                        {"psu_form_factor": psu, "case_supported": case},
                    ),
                    "pass": "电源外形受机箱支持。",
                    "fail": "机箱不支持电源外形。",
                },
            )
        )
        if "gpu" not in products:
            rules.append(
                self._result(
                    "C005", "warning", "未选择独立显卡，无需检查显卡尺寸。", blocking=False
                )
            )
        else:
            rules.append(
                self._c_simple(
                    "C005",
                    products,
                    ["gpu", "case"],
                    {
                        "facts": [
                            (products.get("gpu"), "length_mm"),
                            (products.get("case"), "max_gpu_length_mm"),
                        ],
                        "check": lambda gpu, case: (
                            isinstance(gpu, int) and isinstance(case, int) and gpu <= case,
                            {"gpu_length_mm": gpu, "case_max_gpu_length_mm": case},
                        ),
                        "pass": "显卡长度受当前机箱布局支持。",
                        "fail": "显卡长度超过当前机箱限制。",
                    },
                )
            )
        rules.append(
            self._c_simple(
                "C009",
                products,
                ["storage", "motherboard"],
                {
                    "facts": [
                        (products.get("storage"), "interface"),
                        (products.get("motherboard"), "supported_storage_interfaces"),
                    ],
                    "check": lambda storage, board: (
                        _normalized(storage) in text_set(board),
                        {"storage_interface": storage, "board_supported": board},
                    ),
                    "pass": "存储协议受主板支持。",
                    "fail": "主板不支持该存储协议。",
                },
            )
        )
        rules.append(
            self._c_simple(
                "C010",
                products,
                ["cpu", "motherboard"],
                {
                    "facts": [
                        (products.get("cpu"), "integrated_graphics"),
                        (products.get("motherboard"), "video_output_count"),
                    ],
                    "check": lambda igpu, outputs: (
                        bool(igpu) and isinstance(outputs, int) and outputs > 0,
                        {"integrated_graphics": igpu, "video_output_count": outputs},
                    ),
                    "pass": "无独显时 CPU 核显与主板输出可用。",
                    "fail": "无独显时没有已核验的可用显示输出。",
                },
            )
        )
        return rules

    def _c008(self, products):
        cpu, psu = products.get("cpu"), products.get("psu")
        gpu = products.get("gpu")
        if not cpu or not psu:
            return self._result("C008", "unknown", "缺少 CPU 或电源，无法检查功率与连接器。")
        facts = [
            self._unconditional(cpu["facts"], "max_power_w"),
            self._unconditional(psu["facts"], "rated_power_w"),
        ]
        if gpu:
            facts += [
                self._unconditional(gpu["facts"], "board_power_w"),
                self._unconditional(gpu["facts"], "required_pcie_connector_count"),
                self._unconditional(psu["facts"], "pcie_connector_count"),
            ]
        if any(fact is None or not isinstance(fact["value"], int) for fact in facts):
            return self._result("C008", "unknown", "缺少精确功率或 PCIe 连接器事实。")
        cpu_power, psu_power = facts[0]["value"], facts[1]["value"]
        gpu_power, required_connectors, available_connectors = (
            (0, 0, 0) if not gpu else (facts[2]["value"], facts[3]["value"], facts[4]["value"])
        )
        required_power = ceil((cpu_power + gpu_power + 75) * 1.25)
        passed = psu_power >= required_power and available_connectors >= required_connectors
        return self._result(
            "C008",
            "pass" if passed else "fail",
            "电源功率和连接器满足保守估算。" if passed else "电源功率或 PCIe 连接器不足。",
            facts,
            required_power_w=required_power,
            rated_power_w=psu_power,
            required_pcie_connectors=required_connectors,
            available_pcie_connectors=available_connectors,
        )

    def _c011(self, products, requirements):
        if not requirements:
            return self._result(
                "C011", "warning", "没有明确的 Wi-Fi、USB 或扩展槽硬需求。", blocking=False
            )
        board = products.get("motherboard")
        if not board:
            return self._result("C011", "unknown", "缺少主板，无法检查明确硬需求。")
        key_map = {"wifi": "wifi", "usb_ports": "usb_port_count", "pcie_slots": "pcie_slot_count"}
        facts = {name: self._unconditional(board["facts"], key_map[name]) for name in requirements}
        if any(fact is None for fact in facts.values()):
            return self._result(
                "C011",
                "unknown",
                "缺少明确硬需求对应的主板规格事实。",
                missing_requirements=list(requirements),
            )
        passed = all(
            (
                facts[name]["value"] is value
                if isinstance(value, bool)
                else isinstance(facts[name]["value"], int) and facts[name]["value"] >= value
            )
            for name, value in requirements.items()
        )
        return self._result(
            "C011",
            "pass" if passed else "fail",
            "主板满足明确硬需求。" if passed else "主板不满足明确硬需求。",
            list(facts.values()),
            requirements=requirements,
        )

    def _c012(self, products):
        required = {"cpu", "motherboard", "memory", "storage", "psu", "case"}
        missing = sorted(required - set(products))
        if missing:
            return self._result("C012", "unknown", "清单缺少必要零件。", missing_slots=missing)
        cpu = products["cpu"]
        bundled = self._unconditional(cpu["facts"], "includes_cooler")
        if bundled is None:
            return self._result("C012", "unknown", "缺少 CPU 是否自带散热器的包装事实。")
        if bundled["value"] is False and "cooler" not in products:
            return self._result("C012", "fail", "CPU 不含散热器且清单未提供散热器。", [bundled])
        return self._result(
            "C012", "pass", "必要零件和散热器状态完整。", [bundled], bundled_cooler=bundled["value"]
        )

    def check(self, request):
        products, version = self._load(request)
        results = (
            [
                self._c001(products),
                self._c002(products, request.bios_version),
                self._c003(products),
            ]
            + self._additional(products)
            + [
                self._c008(products),
                self._c011(products, request.hard_requirements),
                self._c012(products),
            ]
        )
        failures = any(result["status"] == "fail" for result in results)
        unknowns = any(result["blocking"] and result["status"] == "unknown" for result in results)
        return {
            "rule_version": RULE_VERSION,
            "status": "incompatible"
            if failures
            else "needs_verification"
            if unknowns
            else "validated",
            "results": results,
            "unexecuted_rule_ids": UNEXECUTED,
            "data_version": version,
            "generated_at": self.catalog.clock(),
        }
