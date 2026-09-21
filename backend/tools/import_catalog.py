"""Bounded manual CLI using the same service as HTTP. Secrets stay out of command arguments."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.common.config import Settings
from app.ingestion.auth import authenticate
from app.ingestion.contracts import ImportInput, PublishInput, ReviewInput
from app.ingestion.service import ImportService
from app.profiles.service import DomainError


def read_json(path):
    with Path(path).open("rb") as handle:
        data = handle.read(1048577)
    if len(data) > 1048576:
        raise ValueError("Input exceeds 1 MiB")
    return json.loads(data)


def main():
    parser = argparse.ArgumentParser(
        description="Manual import; output JSON contains no credentials"
    )
    parser.add_argument(
        "action", choices=["preview", "stage", "resume", "review", "publish", "dispatch"]
    )
    parser.add_argument(
        "--file", help="Batch JSON for preview/stage; decision JSON for review/publish"
    )
    parser.add_argument("--job", type=UUID)
    parser.add_argument("--dry-run", action="store_true", help="preview/stage only; never persists")
    parser.add_argument(
        "--source", type=UUID, help="Assert batch source ID, never an arbitrary URL"
    )
    parser.add_argument("--since", help="Explicitly unsupported for complete manual batches")
    args = parser.parse_args()
    if args.since:
        parser.error(
            "--since is reserved for incremental adapters; manual-v1 requires the complete batch"
        )
    if args.dry_run and args.action not in {"stage", "preview"}:
        parser.error("--dry-run only applies to preview/stage")
    settings = Settings()
    engine = None
    try:
        actor = authenticate(settings, "Bearer " + os.environ.get("ADMIN_TOKEN", ""))
        engine = create_engine(
            settings.database_url.get_secret_value(), connect_args={"connect_timeout": 3}
        )
        service = ImportService(engine, settings, actor)
        if args.action in {"preview", "stage"}:
            batch = ImportInput.model_validate(read_json(args.file))
            if args.source and args.source != batch.source_id:
                raise ValueError("Source assertion does not match batch")
            result = (
                service.preview(batch)
                if args.dry_run or args.action == "preview"
                else service.stage(batch)
            )
        elif args.action == "resume":
            result = service.get(args.job)
        elif args.action == "review":
            result = service.review(args.job, ReviewInput.model_validate(read_json(args.file)))
        elif args.action == "publish":
            result = service.publish(args.job, PublishInput.model_validate(read_json(args.file)))
        else:
            result = service.dispatch()
        print(
            result.model_dump_json(indent=2)
            if hasattr(result, "model_dump_json")
            else json.dumps(result, default=str, indent=2)
        )
    except DomainError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        return 1
    except (ValidationError, ValueError, TypeError, OSError, SQLAlchemyError):
        print(
            json.dumps(
                {
                    "error": "INVALID_INPUT_OR_DEPENDENCY",
                    "message": "Check input, configuration and migration; no changes committed.",
                }
            )
        )
        return 1
    finally:
        if engine:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
