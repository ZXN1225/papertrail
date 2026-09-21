"""Validate non-production evaluation metadata without running a model or production data."""

import argparse
import json
from pathlib import Path

REQUIRED = {"case_id", "group", "expected_status", "forbidden_claims"}


def validate(dataset: dict) -> list[str]:
    errors = []
    if dataset.get("synthetic") is not True:
        errors.append("dataset must declare synthetic=true")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases must be a non-empty list"]
    seen = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or REQUIRED - set(case):
            errors.append(f"case {index} lacks required fields")
            continue
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id.startswith("TEST-GOLD-"):
            errors.append(f"case {index} must use a TEST-GOLD-* id")
        if case_id in seen:
            errors.append(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(case["forbidden_claims"], list) or not case["forbidden_claims"]:
            errors.append(f"case {case_id} must include forbidden_claims")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    errors = validate(json.loads(args.dataset.read_text(encoding="utf-8")))
    if errors:
        raise SystemExit("Invalid evaluation dataset:\n- " + "\n- ".join(errors))
    print(f"PASS: {args.dataset.name} is an isolated synthetic safety dataset.")


if __name__ == "__main__":
    main()
