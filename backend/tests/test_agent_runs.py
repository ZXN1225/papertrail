from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent.contracts import AgentResponse
from app.config import Settings
from app.main import create_app
from app.storage.repository import PaperStore


def test_agent_run_ledger_stores_redacted_state_and_rejects_duplicate_ids() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        question = "TEST question with private context"
        prior_turns = [("user", "TEST prior question"), ("assistant", "TEST prior answer")]

        assert store.create_agent_run(run_id, question, prior_turns)
        assert not store.create_agent_run(run_id, question)
        running = store.get_agent_run(run_id)
        assert running is not None
        assert running["status"] == "running"
        assert running["question_sha256"] == hashlib.sha256(question.encode()).hexdigest()
        expected_history = json.dumps(prior_turns, ensure_ascii=False, separators=(",", ":"))
        assert running["history_sha256"] == hashlib.sha256(expected_history.encode()).hexdigest()
        assert "question" not in running and "answer" not in running
        assert "TEST prior" not in str(running)

        response = AgentResponse(
            status="completed",
            answer="TEST answer containing text that must not be persisted",
            total_observed_tokens=9,
            model_input_tokens=5,
            model_output_tokens=4,
        )
        store.finish_agent_run(run_id, response)
        completed = store.get_agent_run(run_id)

        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["result_status"] == "completed"
        assert completed["total_observed_tokens"] == 9
        assert "TEST answer" not in str(completed)


def test_history_digest_migration_preserves_existing_run_rows() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "legacy-runs.sqlite3"
        migration_directory = Path(__file__).parents[1] / "app/storage/migrations"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript(
                (migration_directory / "0008_agent_runs.sql").read_text(encoding="utf-8")
            )
            connection.execute(
                """INSERT INTO agent_runs (
                    run_id, question_sha256, status, created_at, updated_at
                ) VALUES ('TEST-legacy-run', ?, 'completed', '2026-10-10', '2026-10-10')""",
                ("a" * 64,),
            )
            connection.executescript(
                (migration_directory / "0010_agent_run_history_digest.sql").read_text(
                    encoding="utf-8"
                )
            )
            row = connection.execute(
                "SELECT run_id, history_sha256 FROM agent_runs WHERE run_id='TEST-legacy-run'"
            ).fetchone()
        assert row == (
            "TEST-legacy-run",
            hashlib.sha256(b"[]").hexdigest(),
        )


def test_agent_task_status_marks_orphaned_running_task_interrupted() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        settings = Settings(_env_file=None, data_storage_path=database_path)
        run_id = uuid4()
        store = PaperStore(database_path)
        assert store.create_agent_run(str(run_id), "TEST interrupted request")

        response = TestClient(create_app(settings)).get(f"/api/v1/agent/runs/{run_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "interrupted"
        assert "TEST interrupted request" not in response.text


def test_agent_request_run_id_is_idempotent_and_pollable() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temporary_dir) / "runs.sqlite3")
        client = TestClient(create_app(settings))
        run_id = str(uuid4())

        first = client.post(
            "/api/v1/agent/ask",
            json={
                "question": "TEST ask while model disabled",
                "run_id": run_id,
                "history": [
                    {"role": "user", "content": "TEST first question"},
                    {"role": "assistant", "content": "TEST first answer"},
                ],
            },
        )
        duplicate = client.post(
            "/api/v1/agent/ask",
            json={"question": "TEST ask while model disabled", "run_id": run_id},
        )
        status_response = client.get(f"/api/v1/agent/runs/{run_id}")

        assert first.status_code == 503
        assert first.json()["run_id"] == run_id
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "duplicate_run_id"
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "failed"
        assert status_response.json()["result_status"] == "model_disabled"
        history_material = json.dumps(
            [
                ["user", "TEST first question"],
                ["assistant", "TEST first answer"],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        assert (
            status_response.json()["history_sha256"]
            == hashlib.sha256(history_material.encode()).hexdigest()
        )


def test_unverifiable_provider_usage_returns_503_and_failed_run(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temporary_dir) / "runs.sqlite3")
        client = TestClient(create_app(settings))
        run_id = str(uuid4())

        def stop_for_unknown_usage(
            _service,
            _question: str,
            *,
            history=(),
            cancellation_requested=None,
        ) -> AgentResponse:
            del history, cancellation_requested
            return AgentResponse(
                status="usage_unavailable",
                answer="Provider usage could not be verified.",
            )

        monkeypatch.setattr("app.main.AgentService.ask", stop_for_unknown_usage)
        response = client.post(
            "/api/v1/agent/ask",
            json={"question": "TEST unknown provider usage", "run_id": run_id},
        )
        status_response = client.get(f"/api/v1/agent/runs/{run_id}")

        assert response.status_code == 503
        assert response.json()["status"] == "usage_unavailable"
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "failed"
        assert status_response.json()["result_status"] == "usage_unavailable"


def test_agent_run_cancel_endpoint_signals_only_the_requested_active_run() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        application = create_app(
            Settings(_env_file=None, data_storage_path=Path(temporary_dir) / "runs.sqlite3")
        )
        run_id = str(uuid4())
        cancellation = threading.Event()
        application.state.active_agent_runs[run_id] = cancellation

        response = TestClient(application).post(f"/api/v1/agent/runs/{run_id}/cancel")

        assert response.status_code == 200
        assert response.json() == {
            "run_id": run_id,
            "status": "running",
            "cancellation_requested": True,
        }
        assert cancellation.is_set()


def test_active_run_cancellation_api_finishes_and_persists_cancelled_state(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        application = create_app(
            Settings(_env_file=None, data_storage_path=Path(temporary_dir) / "runs.sqlite3")
        )
        client = TestClient(application)
        started = threading.Event()
        run_id = str(uuid4())
        result: dict[str, object] = {}

        def blocking_ask(
            _service,
            _question: str,
            *,
            history=(),
            cancellation_requested=None,
        ) -> AgentResponse:
            del history
            started.set()
            deadline = time.monotonic() + 5
            while cancellation_requested is not None and not cancellation_requested():
                if time.monotonic() >= deadline:
                    raise TimeoutError("test cancellation was not observed")
                time.sleep(0.005)
            return AgentResponse(status="cancelled", answer="Cancelled at a safe boundary.")

        monkeypatch.setattr("app.main.AgentService.ask", blocking_ask)

        def post_question() -> None:
            result["response"] = client.post(
                "/api/v1/agent/ask",
                json={"question": "TEST cancellation flow", "run_id": run_id},
            )

        request_thread = threading.Thread(target=post_question, daemon=True)
        request_thread.start()
        assert started.wait(timeout=3)

        cancel_response = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
        request_thread.join(timeout=5)
        status_response = client.get(f"/api/v1/agent/runs/{run_id}")

        assert not request_thread.is_alive()
        ask_response = result["response"]
        assert hasattr(ask_response, "status_code")
        assert ask_response.status_code == 200
        assert ask_response.json()["status"] == "cancelled"
        assert cancel_response.status_code == 200
        assert cancel_response.json()["cancellation_requested"] is True
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "cancelled"
        assert status_response.json()["result_status"] == "cancelled"
