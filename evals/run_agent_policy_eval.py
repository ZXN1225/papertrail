"""Measure deterministic Agent tool-contract enforcement without calling an LLM."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.contracts import ToolCall  # noqa: E402
from app.agent.tools import FactsArgs, OffersArgs, SearchCatalogArgs  # noqa: E402
from app.compatibility.contracts import CompatibilityRequest  # noqa: E402
from app.knowledge.contracts import KnowledgeSearchRequest  # noqa: E402

SCHEMAS = {
    "search_catalog": SearchCatalogArgs,
    "get_product_facts": FactsArgs,
    "get_offers": OffersArgs,
    "check_compatibility": CompatibilityRequest,
    "retrieve_knowledge": KnowledgeSearchRequest,
    "rank_laptops": None,
    "solve_pc_builds": None,
}


def is_allowed(case):
    try:
        call = ToolCall.model_validate({"name": case["tool"], "arguments": case["arguments"]})
        schema = SCHEMAS[call.name]
        if schema is None:
            return not call.arguments
        schema.model_validate(call.arguments)
        return True
    except (KeyError, ValueError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    data = json.loads(raw)
    cases = data.get("cases", [])
    if (
        data.get("synthetic") is not True
        or not cases
        or not all(case.get("case_id", "").startswith("TEST-") for case in cases)
    ):
        raise SystemExit("Only TEST-only synthetic policy fixtures are accepted")
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)) or any(
        not isinstance(case.get("expected_allowed"), bool) for case in cases
    ):
        raise SystemExit("Policy case IDs must be unique and expected_allowed must be boolean")
    results = [(case["expected_allowed"], is_allowed(case)) for case in cases]
    true_accepts = sum(expected and actual for expected, actual in results)
    false_accepts = sum(not expected and actual for expected, actual in results)
    true_denials = sum(not expected and not actual for expected, actual in results)
    missed_allowed = sum(expected and not actual for expected, actual in results)
    report = {
        "dataset_id": data["dataset_id"],
        "synthetic": True,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "cases": len(results),
        "correct": sum(expected == actual for expected, actual in results),
        "accuracy": round(
            sum(expected == actual for expected, actual in results) / len(results), 6
        ),
        "allowed_calls_accepted": true_accepts,
        "forbidden_calls_rejected": true_denials,
        "forbidden_calls_accepted": false_accepts,
        "allowed_calls_rejected": missed_allowed,
        "scope": (
            "typed tool name and argument contracts only; no LLM, database or side-effect execution"
        ),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output if args.output.is_absolute() else ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
