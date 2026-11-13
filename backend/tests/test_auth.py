import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app.auth import SESSION_COOKIE, token_digest, verify_password
from app.config import Settings
from app.main import create_app


def test_account_login_and_private_library_are_scoped(tmp_path) -> None:
    settings = Settings(_env_file=None, data_storage_path=tmp_path / "auth.sqlite3")
    client_a = TestClient(create_app(settings))
    client_b = TestClient(create_app(settings))
    password = "correct horse battery staple"

    created = client_a.post(
        "/api/v1/auth/register", json={"username": "Researcher_1", "password": password}
    )
    assert created.status_code == 201
    assert (
        client_b.post(
            "/api/v1/auth/register", json={"username": "researcher_1", "password": password}
        ).status_code
        == 409
    )
    assert (
        client_b.post(
            "/api/v1/auth/register", json={"username": "Researcher_2", "password": password}
        ).status_code
        == 201
    )
    assert (
        client_a.post(
            "/api/v1/library", json={"source": "arxiv", "source_id": "2401.12345"}
        ).status_code
        == 401
    )

    assert (
        client_a.post(
            "/api/v1/auth/login", json={"username": "researcher_1", "password": password}
        ).status_code
        == 200
    )
    assert (
        client_b.post(
            "/api/v1/auth/login", json={"username": "Researcher_1", "password": "wrong password"}
        ).status_code
        == 401
    )
    added = client_a.post(
        "/api/v1/library",
        json={
            "source": "arxiv",
            "source_id": "2401.12345",
            "metadata": {
                "id": "2401.12345",
                "sourceUrl": "https://arxiv.org/abs/2401.12345",
                "title": "TEST saved paper: Evidence-Aware Retrieval-Augmented Generation",
            },
        },
    )
    assert added.status_code == 201
    saved = client_a.get("/api/v1/library").json()[0]
    assert saved["source_id"] == "2401.12345"
    assert (
        saved["metadata"]["title"]
        == "TEST saved paper: Evidence-Aware Retrieval-Augmented Generation"
    )
    assert client_a.get("/api/v1/library", params={"query": "saved"}).json() == [saved]
    assert client_a.get(
        "/api/v1/library", params={"query": "retrieval augmented generation"}
    ).json() == [saved]
    assert client_a.get("/api/v1/library", params={"query": "absent"}).json() == []
    assert (
        client_b.post(
            "/api/v1/auth/login", json={"username": "Researcher_2", "password": password}
        ).status_code
        == 200
    )
    assert client_b.get("/api/v1/library").json() == []
    conversation = client_a.post("/api/v1/conversations", json={"title": "TEST private"})
    assert conversation.status_code == 201
    renamed = client_a.patch(
        f"/api/v1/conversations/{conversation.json()['id']}",
        json={"title": "TEST renamed conversation"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "TEST renamed conversation"
    assert (
        client_b.get(f"/api/v1/conversations/{conversation.json()['id']}/messages").status_code
        == 404
    )
    assert (
        client_b.patch(
            f"/api/v1/conversations/{conversation.json()['id']}",
            json={"title": "TEST unauthorized rename"},
        ).status_code
        == 404
    )
    assert client_b.delete(f"/api/v1/conversations/{conversation.json()['id']}").status_code == 404
    assert client_a.delete(f"/api/v1/conversations/{conversation.json()['id']}").status_code == 204
    assert (
        client_a.get(f"/api/v1/conversations/{conversation.json()['id']}/messages").status_code
        == 404
    )
    assert client_a.post("/api/v1/auth/logout").status_code == 200
    assert client_a.get("/api/v1/library").status_code == 401


def test_agent_turns_are_saved_to_the_owned_conversation(tmp_path, monkeypatch) -> None:
    from app import main as main_module
    from app.agent.contracts import AgentResponse, Citation, EvidenceSpan

    observed_library: list[tuple[str, str]] = []
    observed_users: list[str] = []
    observed_histories: list[list[tuple[str, str]]] = []

    class FakeAgentService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ask(self, *_args, **kwargs) -> AgentResponse:
            observed_library.extend(kwargs["user_library"])
            observed_users.append(kwargs["user_id"])
            observed_histories.append([(turn.role, turn.content) for turn in kwargs["history"]])
            return AgentResponse(
                status="completed",
                answer="TEST synthetic answer",
                context_state={"objective": "TEST objective"},
                citations=[
                    Citation(
                        openalex_id="W100",
                        title="TEST synthetic source",
                        source_url="https://openalex.org/W100",
                        evidence=[
                            EvidenceSpan(
                                chunk_id="TEST-chunk",
                                locator="TEST page 1",
                                excerpt="TEST synthetic evidence",
                            )
                        ],
                    )
                ],
            )

    monkeypatch.setattr(main_module, "AgentService", FakeAgentService)
    client = TestClient(
        create_app(Settings(_env_file=None, data_storage_path=tmp_path / "conversation.sqlite3"))
    )
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"username": "conversation_owner", "password": "correct horse battery staple"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "conversation_owner", "password": "correct horse battery staple"},
        ).status_code
        == 200
    )
    authenticated_user_id = client.get("/api/v1/auth/me").json()["id"]
    assert (
        client.post(
            "/api/v1/library", json={"source": "arxiv", "source_id": "2401.12345"}
        ).status_code
        == 201
    )
    conversation = client.post("/api/v1/conversations", json={"title": "新对话"}).json()

    answer = client.post(
        "/api/v1/agent/ask",
        json={"question": "TEST question", "conversation_id": conversation["id"]},
    )

    assert answer.status_code == 200
    assert observed_library == [("arxiv", "2401.12345")]
    assert observed_users == [authenticated_user_id]
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "TEST question"),
        ("assistant", "TEST synthetic answer"),
    ]
    assert messages[0]["response"] is None
    assert messages[1]["response"]["citations"][0]["evidence"][0]["excerpt"] == (
        "TEST synthetic evidence"
    )
    assert messages[1]["response"]["context_state"]["objective"] == "TEST objective"
    second = client.post(
        "/api/v1/agent/ask",
        json={"question": "TEST followup", "conversation_id": conversation["id"]},
    )
    assert second.status_code == 200
    assert observed_histories[1] == [
        ("user", "TEST question"),
        ("assistant", "TEST synthetic answer"),
    ]
    assert [
        m["role"] for m in client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()
    ] == ["user", "assistant", "user", "assistant"]
    listed = client.get("/api/v1/conversations").json()
    assert listed[0]["title"] == "TEST question"
    assert client.delete(f"/api/v1/conversations/{conversation['id']}/messages").status_code == 204
    assert client.get(f"/api/v1/conversations/{conversation['id']}/messages").json() == []


def test_interrupted_agent_log_includes_run_id_without_exception_details(
    tmp_path, monkeypatch, caplog
) -> None:
    from app import main as main_module

    class FailingAgentService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def ask(self, *_args, **_kwargs):
            raise RuntimeError("TEST private exception detail")

    monkeypatch.setattr(main_module, "AgentService", FailingAgentService)
    client = TestClient(
        create_app(Settings(_env_file=None, data_storage_path=tmp_path / "interrupted.sqlite3"))
    )
    client.post(
        "/api/v1/auth/register",
        json={"username": "interrupted_owner", "password": "correct horse battery staple"},
    )
    client.post(
        "/api/v1/auth/login",
        json={"username": "interrupted_owner", "password": "correct horse battery staple"},
    )

    response = client.post("/api/v1/agent/ask", json={"question": "TEST question"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "agent_run_interrupted"
    run_id = response.json()["detail"]["run_id"]
    assert run_id in caplog.text
    assert "RuntimeError" in caplog.text
    assert "TEST private exception detail" not in caplog.text


def test_password_and_session_are_hashed_and_expired_sessions_are_rejected(tmp_path) -> None:
    password = "correct horse battery staple"
    database_path = tmp_path / "credentials.sqlite3"
    client = TestClient(create_app(Settings(_env_file=None, data_storage_path=database_path)))
    client.post("/api/v1/auth/register", json={"username": "hash_check", "password": password})
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "hash_check", "password": password}
        ).status_code
        == 200
    )
    token = client.cookies.get(SESSION_COOKIE)
    assert token

    with closing(sqlite3.connect(database_path)) as db:
        password_hash = db.execute("SELECT password_hash FROM users").fetchone()[0]
        session_hash = db.execute("SELECT token_sha256 FROM user_sessions").fetchone()[0]
        db.execute("UPDATE user_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
        db.commit()
    assert password not in password_hash
    assert verify_password(password, password_hash)
    assert session_hash == token_digest(token)
    assert token not in session_hash
    assert client.get("/api/v1/auth/me").status_code == 401


def test_auth_rate_limit_is_shared_between_app_instances(tmp_path) -> None:
    database_path = tmp_path / "shared-auth-limit.sqlite3"
    settings = Settings(_env_file=None, data_storage_path=database_path)
    first = TestClient(create_app(settings))
    second = TestClient(create_app(settings))
    payload = {"username": "shared_limit", "password": "correct horse battery staple"}

    statuses = [first.post("/api/v1/auth/register", json=payload).status_code]
    statuses.extend(first.post("/api/v1/auth/register", json=payload).status_code for _ in range(7))
    assert statuses == [201] + [409] * 7
    assert second.post("/api/v1/auth/register", json=payload).status_code == 429
