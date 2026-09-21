"""Report P7 release blockers without exposing environment values or mutating services."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    dataset = json.loads(
        (ROOT / "evals/datasets/synthetic-safety-v1.json").read_text(encoding="utf-8")
    )
    checks = [
        ("real_source_authorization", False, "D01-D03 remain blocked"),
        ("human_reviewed_gold_set", False, "0 / 120 human-reviewed cases"),
        ("model_cost_evaluation", False, "LLM provider is disabled"),
        ("deployment_target", False, "server, domain, TLS, and credentials are not supplied"),
        ("synthetic_safety_fixture", bool(dataset.get("synthetic")), f"{len(dataset['cases'])} TEST cases"),
    ]
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'BLOCKED'}: {name} — {detail}")
    if not all(passed for _, passed, _ in checks):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
