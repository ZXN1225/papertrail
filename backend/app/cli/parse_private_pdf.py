"""Parse one private PDF in a bounded local worker process."""

import json
import os
import sys
from pathlib import Path

from app.retrieval.pdf_parser import parse_pdf_bytes_mineru, read_pdf_bytes


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(2)
    from mineru.config import get_config

    if get_config().model.vlm.server_url:
        raise SystemExit(3)
    source, destination = (Path(value) for value in sys.argv[1:])
    tier = os.getenv("PAPERTRAIL_MINERU_TIER", "standard").strip().lower()
    parsed = parse_pdf_bytes_mineru(read_pdf_bytes(source), tier=tier)
    destination.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
