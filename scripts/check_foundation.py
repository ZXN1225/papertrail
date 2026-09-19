"""Check the planning scaffold only; this is not an application test suite."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "AGENTS.md", ".env.example", ".gitignore", ".editorconfig",
    "docs/PROJECT_SPEC.md", "docs/EXECUTION_PLAN.md", "docs/TASKS.md",
    "docs/PROGRESS.md", "docs/adr/README.md", "docs/data-sources.md",
    "docs/data-dictionary.md", "docs/api-contract.md", "docs/reviews/T01-PR.md",
    "backend/README.md", "web/README.md", "deploy/README.md",
    "evals/README.md", "data/README.md",
)


def main() -> int:
    errors = []
    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"Missing or empty: {name}")

    for name in ("data/manifests/source.template.json", "data/samples/collection.template.json"):
        try:
            value = json.loads((ROOT / name).read_text(encoding="utf-8"))
            if value.get("is_template") is not True or value.get("publishable") is not False:
                errors.append(f"Template must be marked non-publishable: {name}")
        except (OSError, ValueError, AttributeError) as exc:
            errors.append(f"Invalid template {name}: {exc}")

    env_path = ROOT / ".env.example"
    if env_path.is_file():
        env = dict(line.split("=", 1) for line in env_path.read_text(encoding="utf-8").splitlines()
                   if line and not line.startswith("#") and "=" in line)
        for key in ("DATABASE_URL", "REDIS_URL", "SESSION_SIGNING_SECRET", "ADMIN_AUTH_CONFIG",
                    "LLM_API_KEY", "SOURCE_CREDENTIALS_REFERENCE"):
            if env.get(key) != "":
                errors.append(f"Expected an empty placeholder: {key}")
        if env.get("LLM_PROVIDER") != "disabled":
            errors.append("Default LLM provider must be disabled")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(REQUIRED)} foundation files, 2 non-publishable JSON templates, safe config defaults.")
    print("Scope: scaffold only. Application, database, sources and business behavior are not tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
