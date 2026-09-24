"""Export the checked FastAPI contract for review and client generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.main import app


def main() -> None:
    output = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
    serialized = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    output.write_text(serialized, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    print(f"OpenAPI contract exported: {output} sha256={digest}")


if __name__ == "__main__":
    main()
