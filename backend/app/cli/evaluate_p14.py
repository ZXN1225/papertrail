"""Compare BM25, Dense and RRF on the explicitly exploratory P13 dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.embeddings.client import EmbeddingError, OpenAIEmbeddingClient
from app.evaluation.p14 import P14EvaluationError, run_p14_comparison
from app.storage.repository import PaperStore

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "data/evaluation/p13_ai_labeled_v1.json"
RUNNER_PATH = Path(__file__).resolve().parents[1] / "evaluation/p14.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/p14-retrieval-comparison.json")
    )
    parser.add_argument(
        "--allow-provider-call",
        action="store_true",
        help="explicitly authorize a bounded OpenAI embeddings request and associated account cost",
    )
    args = parser.parse_args(argv)
    if not args.allow_provider_call:
        print(
            "P14 needs embeddings. Re-run with --allow-provider-call to authorize "
            "the bounded API call.",
            file=sys.stderr,
        )
        return 2

    client = None
    try:
        raw = args.dataset.read_bytes()
        dataset = json.loads(raw)
        settings = get_settings()
        client = OpenAIEmbeddingClient(settings)
        report = run_p14_comparison(
            PaperStore(settings.resolved_data_storage_path),
            dataset,
            hashlib.sha256(raw).hexdigest(),
            client,
            price_per_million_usd=settings.embedding_price_per_million_usd,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RuntimeError,
        EmbeddingError,
        P14EvaluationError,
    ) as error:
        safe_code = error.code if isinstance(error, EmbeddingError) else type(error).__name__
        print(f"P14 evaluation failed: {safe_code}", file=sys.stderr)
        return 2
    finally:
        if client is not None:
            client.close()

    report["reproducibility"] = {
        "command": "python -m app.cli.evaluate_p14 --allow-provider-call",
        "dataset_path": args.dataset.as_posix(),
        "runner_sha256": hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "dataset_sha256": report["dataset"]["sha256"],
                "snapshot_id": report["corpus"]["snapshot_id"],
                "document_count": report["corpus"]["document_count"],
                "query_count": report["corpus"]["query_count"],
                "quality_claim_allowed": report["dataset"]["quality_claim_allowed"],
                "embedding_model": report["embedding"]["model"],
                "embedding_input_tokens": report["embedding"]["input_tokens"],
                "estimated_cost_usd": report["embedding"]["estimated_cost_usd"],
                "methods": report["methods"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
