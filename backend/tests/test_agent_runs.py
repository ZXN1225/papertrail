from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agent.contracts import AgentResponse, AgentTraceEvent, SkillUsage
from app.config import Settings
from app.main import create_app
from app.storage.repository import DailyAgentTokenBudgetExceeded, PaperStore


def _authenticate(client: TestClient, username: str = "AgentTestUser") -> str:
    credentials = {"username": username, "password": "TEST password secure 123"}
    client.post("/api/v1/auth/register", json=credentials)
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
    return client.get("/api/v1/auth/me").json()["id"]


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
        client = TestClient(create_app(settings))
        owner = _authenticate(client)
        assert store.create_agent_run(str(run_id), "TEST interrupted request", user_id=owner)
        with store._connection() as connection:
            connection.execute(
                "UPDATE agent_runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE run_id = ?",
                (str(run_id),),
            )

        response = client.get(f"/api/v1/agent/runs/{run_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "interrupted"
        assert "TEST interrupted request" not in response.text


def test_live_remote_worker_is_not_marked_interrupted_and_cancel_is_persisted() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        application = create_app(Settings(_env_file=None, data_storage_path=database_path))
        client = TestClient(application)
        owner = _authenticate(client)
        store = PaperStore(database_path)
        run_id = str(uuid4())
        assert store.create_agent_run(
            run_id,
            "TEST remote worker request",
            user_id=owner,
            worker_id="TEST-other-worker",
        )

        status_response = client.get(f"/api/v1/agent/runs/{run_id}")
        cancel_response = client.post(f"/api/v1/agent/runs/{run_id}/cancel")
        run = store.get_agent_run(run_id, owner)

        assert status_response.status_code == 200
        assert status_response.json()["status"] == "running"
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "running"
        assert cancel_response.json()["cancellation_requested"] is True
        assert run is not None and run["cancel_requested_at"]
        assert run["phase"] == "cancel_requested"


def test_run_lease_renews_only_for_owning_worker_and_expiry_is_detected() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        assert store.create_agent_run(run_id, "TEST lease", worker_id="TEST-worker")

        assert not store.is_agent_run_lease_expired(run_id)
        assert not store.renew_agent_run_lease(run_id, "TEST-other-worker")
        assert store.renew_agent_run_lease(run_id, "TEST-worker")
        with store._connection() as connection:
            connection.execute(
                "UPDATE agent_runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE run_id = ?",
                (run_id,),
            )
        assert store.is_agent_run_lease_expired(run_id)


def test_killed_worker_is_recovered_by_a_new_app_instance() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        ready_path = Path(temporary_dir) / "worker-ready"
        settings = Settings(_env_file=None, data_storage_path=database_path)
        client = TestClient(create_app(settings))
        owner = _authenticate(client)
        run_id = str(uuid4())
        worker_id = "TEST-subprocess-worker"
        worker_code = "\n".join(
            [
                "import sys, time",
                "from pathlib import Path",
                "from app.storage.repository import PaperStore",
                "db, run, owner, worker, ready = sys.argv[1:]",
                "store = PaperStore(Path(db))",
                "created = store.create_agent_run(\n"
                "    run, 'TEST killed worker', user_id=owner, worker_id=worker\n"
                ")",
                "assert created",
                "store.set_agent_run_phase(run, 'executing')",
                "Path(ready).write_text('ready')",
                "while True:",
                "    store.renew_agent_run_lease(run, worker)",
                "    time.sleep(0.05)",
            ]
        )
        worker = subprocess.Popen(
            [
                sys.executable,
                "-c",
                worker_code,
                str(database_path),
                run_id,
                owner,
                worker_id,
                str(ready_path),
            ],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 8
        while not ready_path.exists() and worker.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready_path.exists():
            stdout, stderr = worker.communicate(timeout=2)
            raise AssertionError(f"TEST worker failed to start: {stdout}\n{stderr}")

        worker.terminate()
        worker.wait(timeout=3)
        store = PaperStore(database_path)
        with store._connection() as connection:
            connection.execute(
                "UPDATE agent_runs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE run_id=?",
                (run_id,),
            )

        restarted_client = TestClient(create_app(settings))
        _authenticate(restarted_client)
        recovered = restarted_client.get(f"/api/v1/agent/runs/{run_id}")

        assert recovered.status_code == 200
        assert recovered.json()["status"] == "interrupted"
        assert recovered.json()["phase"] == "interrupted"
        assert recovered.json()["token_actual"] == 0


def test_cancel_and_worker_recovery_race_has_one_consistent_terminal_state() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        client = TestClient(create_app(Settings(_env_file=None, data_storage_path=database_path)))
        owner = _authenticate(client)
        store = PaperStore(database_path)
        run_id = str(uuid4())
        assert store.create_agent_run(
            run_id, "TEST cancel recovery race", user_id=owner, worker_id="TEST-worker"
        )
        barrier = threading.Barrier(2)
        results: list[bool] = []

        def cancel() -> None:
            barrier.wait()
            requested = store.request_agent_run_cancel(run_id, owner)
            results.append(requested)
            if requested:
                store.resolve_agent_run_stop(run_id)

        def recover() -> None:
            barrier.wait()
            results.append(store.resolve_agent_run_stop(run_id))

        threads = [threading.Thread(target=cancel), threading.Thread(target=recover)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        run = store.get_agent_run(run_id, owner)
        assert all(not thread.is_alive() for thread in threads)
        assert run is not None
        if run["cancel_requested_at"]:
            assert run["status"] == "cancelled"
        else:
            assert run["status"] == "interrupted"


def test_run_progress_persists_redacted_trace_and_token_reservation() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        assert store.create_agent_run(
            run_id, "TEST private question", worker_id="TEST-worker", token_budget=12000
        )
        event = AgentTraceEvent(
            sequence=1,
            kind="model",
            name="responses",
            status="ok",
            duration_ms=14,
            input_tokens=30,
            output_tokens=7,
        )

        assert store.update_agent_run_progress(
            run_id, "TEST-worker", token_reserved=500, token_actual=37, trace=[event]
        )
        run = store.get_agent_run(run_id)

        assert run is not None
        assert run["token_budget"] == 12000
        assert run["token_reserved"] == 500
        assert run["token_actual"] == 37
        assert run["model_input_tokens"] == 30
        assert run["model_output_tokens"] == 7
        assert run["trace"] == [event.model_dump(mode="json")]
        assert "TEST private question" not in str(run)
        assert run["heartbeat_at"]


def test_run_completion_persists_versioned_harness_metadata_without_prompt_text() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        assert store.create_agent_run(
            run_id,
            "TEST version metadata",
            harness_metadata={
                "model_id": "TEST-model-v1",
                "pdf_parser_adapter": "TEST-parser-v1",
                "pdf_chunker_version": "TEST-chunker-v1",
                "task_id": "paper-qa",
                "task_registry_version": "1.0.0",
                "task_registry_sha256": "c" * 64,
                "workflow": ["retrieve", "form_claims", "validate_evidence", "answer"],
                "skill_id": "paper-qa",
                "skill_version": "1.0.0",
                "skill_instructions_sha256": "a" * 64,
                "skill_registry_version": "1.0.0",
                "skill_registry_sha256": "b" * 64,
                "skill_selection_reason": "matched_task_cue",
            },
        )
        skill = SkillUsage(
            skill_id="paper-qa",
            version="1.0.0",
            instructions_sha256="a" * 64,
            allowed_tools=["retrieve_paper_evidence"],
            registry_version="1.0.0",
            registry_sha256="b" * 64,
            selection_reason="matched_task_cue",
            task_id="paper-qa",
            task_registry_version="1.0.0",
            task_registry_sha256="c" * 64,
            workflow=["retrieve", "form_claims", "validate_evidence", "answer"],
            prompt_sha256="d" * 64,
        )
        response = AgentResponse(status="completed", answer="TEST answer", skill=skill)

        store.finish_agent_run(
            run_id,
            response,
            model_id="TEST-model-v1",
            pdf_parser_adapter="TEST-parser-v1",
            pdf_chunker_version="TEST-chunker-v1",
        )
        run = store.get_agent_run(run_id)

        assert run is not None
        assert run["harness_metadata"] == {
            "model_id": "TEST-model-v1",
            "pdf_parser_adapter": "TEST-parser-v1",
            "pdf_chunker_version": "TEST-chunker-v1",
            "task_id": "paper-qa",
            "task_registry_version": "1.0.0",
            "task_registry_sha256": "c" * 64,
            "workflow": ["retrieve", "form_claims", "validate_evidence", "answer"],
            "skill_id": "paper-qa",
            "skill_version": "1.0.0",
            "skill_instructions_sha256": "a" * 64,
            "skill_registry_version": "1.0.0",
            "skill_registry_sha256": "b" * 64,
            "prompt_sha256": "d" * 64,
            "skill_selection_reason": "matched_task_cue",
        }
        assert "TEST answer" not in str(run)


def test_run_start_harness_metadata_survives_worker_interruption() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        metadata = {
            "model_id": "TEST-model-v1",
            "task_id": "citation-check",
            "task_registry_sha256": "a" * 64,
            "skill_id": "citation-check",
            "skill_instructions_sha256": "b" * 64,
        }
        assert store.create_agent_run(
            run_id,
            "TEST interrupted version metadata",
            harness_metadata=metadata,
        )

        assert store.resolve_agent_run_stop(run_id)
        run = store.get_agent_run(run_id)

        assert run is not None
        assert run["status"] == "interrupted"
        assert run["harness_metadata"] == metadata


def test_daily_user_token_budget_reserves_running_runs_and_settles_actual_usage() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        client = TestClient(create_app(Settings(_env_file=None, data_storage_path=database_path)))
        user_id = _authenticate(client)
        store = PaperStore(database_path)
        with pytest.raises(ValueError, match="positive run reservation"):
            store.create_agent_run(
                str(uuid4()),
                "TEST missing run reservation",
                user_id=user_id,
                token_budget=0,
                daily_token_budget=100,
            )
        first_id = str(uuid4())
        assert store.create_agent_run(
            first_id,
            "TEST first run",
            user_id=user_id,
            token_budget=60,
            daily_token_budget=100,
        )
        assert not store.create_agent_run(
            first_id,
            "TEST duplicate retry",
            user_id=user_id,
            token_budget=60,
            daily_token_budget=100,
        )
        with pytest.raises(DailyAgentTokenBudgetExceeded):
            store.create_agent_run(
                str(uuid4()),
                "TEST exceeds reserved daily budget",
                user_id=user_id,
                token_budget=50,
                daily_token_budget=100,
            )

        store.finish_agent_run(
            first_id,
            AgentResponse(
                status="completed",
                answer="TEST answer",
                total_observed_tokens=25,
            ),
        )
        assert store.create_agent_run(
            str(uuid4()),
            "TEST uses settled daily remainder",
            user_id=user_id,
            token_budget=75,
            daily_token_budget=100,
        )
        assert store.create_agent_run(
            str(uuid4()),
            "TEST separate user budget",
            user_id=_authenticate(client, "AgentOtherTestUser"),
            token_budget=100,
            daily_token_budget=100,
        )


def test_concurrent_run_creation_cannot_overreserve_daily_user_budget() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        client = TestClient(create_app(Settings(_env_file=None, data_storage_path=database_path)))
        user_id = _authenticate(client)
        store = PaperStore(database_path)
        store.migrate()
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def create_run() -> None:
            barrier.wait()
            try:
                created = store.create_agent_run(
                    str(uuid4()),
                    "TEST concurrent run",
                    user_id=user_id,
                    token_budget=60,
                    daily_token_budget=100,
                )
                outcomes.append("created" if created else "duplicate")
            except DailyAgentTokenBudgetExceeded:
                outcomes.append("budget_exceeded")

        threads = [threading.Thread(target=create_run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert all(not thread.is_alive() for thread in threads)
        assert sorted(outcomes) == ["budget_exceeded", "created"]


def test_agent_endpoint_rejects_run_when_daily_user_budget_is_reserved() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        database_path = Path(temporary_dir) / "runs.sqlite3"
        settings = Settings(
            _env_file=None,
            data_storage_path=database_path,
            agent_max_total_tokens=256,
            agent_daily_user_token_budget=256,
        )
        client = TestClient(create_app(settings))
        user_id = _authenticate(client)
        assert PaperStore(database_path).create_agent_run(
            str(uuid4()),
            "TEST consume daily budget",
            user_id=user_id,
            token_budget=256,
        )

        response = client.post("/api/v1/agent/ask", json={"question": "TEST request"})

        assert response.status_code == 429
        assert response.json()["detail"] == {
            "code": "daily_agent_token_budget_exceeded",
            "daily_token_budget": 256,
        }


def test_cancel_request_is_scoped_to_run_owner() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "runs.sqlite3")
        run_id = str(uuid4())
        owner = _authenticate(
            TestClient(create_app(Settings(_env_file=None, data_storage_path=store.database_path)))
        )
        assert store.create_agent_run(run_id, "TEST owner scope", user_id=owner)

        assert not store.request_agent_run_cancel(run_id, "TEST-other-owner")
        assert store.request_agent_run_cancel(run_id, owner)
        run = store.get_agent_run(run_id, owner)
        assert run is not None and run["cancel_requested_at"]
        assert run["phase"] == "cancel_requested"


def test_agent_request_run_id_is_idempotent_and_pollable() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temporary_dir) / "runs.sqlite3")
        client = TestClient(create_app(settings))
        _authenticate(client)
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
        _authenticate(client)
        run_id = str(uuid4())

        def stop_for_unknown_usage(
            _service,
            _question: str,
            *,
            history=(),
            prior_user_questions=None,
            memory=None,
            user_library=(),
            user_id="",
            cancellation_requested=None,
            progress_callback=None,
        ) -> AgentResponse:
            del (
                history,
                prior_user_questions,
                user_library,
                user_id,
                cancellation_requested,
                progress_callback,
            )
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
        database_path = Path(temporary_dir) / "runs.sqlite3"
        application = create_app(Settings(_env_file=None, data_storage_path=database_path))
        run_id = str(uuid4())
        cancellation = threading.Event()
        application.state.active_agent_runs[run_id] = cancellation

        client = TestClient(application)
        owner = _authenticate(client)
        assert PaperStore(database_path).create_agent_run(
            run_id, "TEST cancel endpoint", user_id=owner
        )
        response = client.post(f"/api/v1/agent/runs/{run_id}/cancel")

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
        _authenticate(client)
        started = threading.Event()
        run_id = str(uuid4())
        result: dict[str, object] = {}

        def blocking_ask(
            _service,
            _question: str,
            *,
            history=(),
            prior_user_questions=None,
            memory=None,
            user_library=(),
            user_id="",
            cancellation_requested=None,
            progress_callback=None,
        ) -> AgentResponse:
            del history, prior_user_questions, user_library, user_id, progress_callback
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
