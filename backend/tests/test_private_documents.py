import hashlib
import json
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.harness import AgentHarness, _collect_citations
from app.auth import create_account
from app.config import Settings
from app.main import create_app
from app.private_documents import PrivateDocumentService
from app.storage.repository import PaperStore


def test_personal_migration_preserves_existing_document_and_chunks(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite3"
    migrations = Path(__file__).parents[1] / "app" / "storage" / "migrations"
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, "
            "checksum_sha256 TEXT, applied_at TEXT)"
        )
        db.execute(
            "CREATE TABLE user_library_entries (id TEXT, user_id TEXT, PRIMARY KEY (id, user_id))"
        )
        db.execute("INSERT INTO user_library_entries VALUES ('TEST-entry','TEST-owner')")
        db.executescript((migrations / "0015_user_private_documents.sql").read_text())
        db.executescript((migrations / "0016_private_chunker_version.sql").read_text())
        db.executescript((migrations / "0008_agent_runs.sql").read_text())
        db.execute(
            "INSERT INTO user_documents "
            "(id,user_id,library_entry_id,source_type,source_id,title,source_url,"
            "original_filename,storage_key,document_sha256,size_bytes,state,rights_attested_at,"
            "chunk_count,created_at,updated_at,chunker_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "TEST-document",
                "TEST-owner",
                "TEST-entry",
                "arxiv",
                "2401.12345",
                "TEST title",
                "https://arxiv.org/abs/2401.12345",
                "test.pdf",
                "TEST-key.pdf",
                "a" * 64,
                10,
                "queued",
                "2026-11-06",
                1,
                "2026-11-06",
                "2026-11-06",
                "v1",
            ),
        )
        db.execute(
            "INSERT INTO user_document_chunks "
            "(chunk_id,document_id,user_id,ordinal,retrieval_text,evidence_text,locator,"
            "char_start,char_end,page_number,element_type,section_path,content_sha256) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "TEST-chunk",
                "TEST-document",
                "TEST-owner",
                0,
                "text",
                "text",
                "p1",
                0,
                4,
                1,
                "paragraph",
                "[]",
                "a" * 64,
            ),
        )
        for version, path in enumerate(
            sorted(migrations.glob("[0-9][0-9][0-9][0-9]_*.sql"))[:16], 1
        ):
            db.execute(
                "INSERT INTO schema_migrations VALUES (?,?,?,?)",
                (
                    version,
                    path.stem,
                    hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                    "2026-11-06",
                ),
            )
        db.execute("PRAGMA user_version = 16")
    store = PaperStore(database)
    store.migrate()
    with store._connection() as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT library_entry_id FROM user_documents").fetchone()[0] == "TEST-entry"
        )
        assert (
            db.execute("SELECT document_id FROM user_document_chunks").fetchone()[0]
            == "TEST-document"
        )
        db.execute("DELETE FROM user_documents WHERE id='TEST-document'")
        assert db.execute("SELECT COUNT(*) FROM user_document_chunks").fetchone()[0] == 0


def _fake_parse(_pdf_path: object) -> dict[str, object]:
    return {
        "parser_version": "mineru-4.1.test-papertrail-v8",
        "elements": [
            {
                "element_id": "TEST-private-e1",
                "page_number": 1,
                "element_type": "paragraph",
                "text": "TEST private evidence: the synthetic system uses blue widgets.",
                "section_path": ["TEST Results"],
                "bbox": [1, 2, 30, 20],
            },
            {
                "element_id": "TEST-private-table",
                "page_number": 2,
                "element_type": "table",
                "text": "<table><tr><td>tableonlyunitvalue</td></tr></table>",
                "section_path": ["TEST Results"],
                "bbox": [1, 2, 30, 20],
            },
            {
                "element_id": "TEST-private-figure",
                "page_number": 3,
                "element_type": "figure",
                "text": "TEST figureonlycaptionvalue",
                "section_path": ["TEST Results"],
                "bbox": [1, 2, 30, 20],
            },
        ],
        "warnings": [],
    }


def _library_entry(store: PaperStore, user_id: str, entry_id: str) -> None:
    metadata = {
        "id": "2401.12345",
        "sourceUrl": "https://arxiv.org/abs/2401.12345",
        "title": "TEST private paper",
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with store._connection() as db:
        db.execute(
            "INSERT INTO user_library_entries "
            "(id,user_id,source,source_id,added_at,metadata_json,metadata_sha256) "
            "VALUES(?,?,?, ?,?,?,?)",
            (
                entry_id,
                user_id,
                "arxiv",
                "2401.12345",
                "2026-11-06T00:00:00+00:00",
                metadata_json,
                hashlib.sha256(metadata_json.encode()).hexdigest(),
            ),
        )


def test_private_document_upload_quota_is_serialized_across_connections(
    tmp_path, monkeypatch
) -> None:
    from app import private_documents

    store = PaperStore(tmp_path / "papertrail.sqlite3")
    store.migrate()
    owner = create_account(store, "quota_owner", "correct horse battery staple")
    assert owner is not None
    service = PrivateDocumentService(store)
    monkeypatch.setattr(private_documents, "MAX_USER_DOCUMENTS", 1)

    def upload(filename: str) -> str:
        try:
            service.store_upload(
                user_id=owner,
                title="TEST concurrent upload",
                filename=filename,
                pdf_bytes=b"%PDF-TEST-concurrent",
                rights_attested=True,
            )
            return "stored"
        except OverflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(upload, ("first.pdf", "second.pdf")))

    assert results.count("stored") == 1
    assert results.count("user_document_count_limit") == 1
    assert len(service.list_documents(owner)) == 1


def test_private_document_delete_restores_file_when_database_delete_fails(tmp_path) -> None:
    store = PaperStore(tmp_path / "papertrail.sqlite3")
    store.migrate()
    owner = create_account(store, "delete_owner", "correct horse battery staple")
    assert owner is not None
    service = PrivateDocumentService(store)
    uploaded = service.store_upload(
        user_id=owner,
        title="TEST delete rollback",
        filename="delete.pdf",
        pdf_bytes=b"%PDF-TEST-delete-rollback",
        rights_attested=True,
    )
    with store._connection() as db:
        db.execute("UPDATE user_documents SET state='failed' WHERE id=?", (uploaded["id"],))
        db.execute(
            "CREATE TRIGGER TEST_reject_document_delete BEFORE DELETE ON user_documents "
            "BEGIN SELECT RAISE(ABORT, 'TEST delete rejected'); END"
        )

    path = service._path(owner, f"{uploaded['id']}.pdf")
    try:
        service.delete_document(owner, uploaded["id"])
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("database delete trigger should reject deletion")

    assert path.is_file()
    assert not path.with_name(f"{path.name}.deleting").exists()
    assert service.get_document(owner, uploaded["id"]) is not None

    with store._connection() as db:
        db.execute("DROP TRIGGER TEST_reject_document_delete")
    assert service.delete_document(owner, uploaded["id"]) == uploaded["id"]
    assert not path.exists()


def test_pending_documents_recovers_delete_tombstones_after_restart(tmp_path) -> None:
    store = PaperStore(tmp_path / "papertrail.sqlite3")
    store.migrate()
    owner = create_account(store, "delete_recovery_owner", "correct horse battery staple")
    assert owner is not None
    service = PrivateDocumentService(store)
    restore = service.store_upload(
        user_id=owner,
        title="TEST interrupted delete",
        filename="restore.pdf",
        pdf_bytes=b"%PDF-TEST-restore",
        rights_attested=True,
    )
    orphan = service.store_upload(
        user_id=owner,
        title="TEST completed delete",
        filename="orphan.pdf",
        pdf_bytes=b"%PDF-TEST-orphan",
        rights_attested=True,
    )
    restore_path = service._path(owner, f"{restore['id']}.pdf")
    orphan_path = service._path(owner, f"{orphan['id']}.pdf")
    restore_tombstone = restore_path.with_name(f"{restore_path.name}.deleting")
    orphan_tombstone = orphan_path.with_name(f"{orphan_path.name}.deleting")
    restore_path.replace(restore_tombstone)
    orphan_path.replace(orphan_tombstone)
    with store._connection() as db:
        db.execute("DELETE FROM user_documents WHERE id=?", (orphan["id"],))

    service.pending_documents()

    assert restore_path.is_file()
    assert not restore_tombstone.exists()
    assert not orphan_path.exists()
    assert not orphan_tombstone.exists()


def test_private_document_index_and_evidence_are_scoped_to_owner(tmp_path, monkeypatch) -> None:
    from app import private_documents
    from app.agent.tools import PaperToolRegistry

    database = tmp_path / "papertrail.sqlite3"
    store = PaperStore(database)
    owner = create_account(store, "private_owner", "correct horse battery staple")
    other = create_account(store, "private_other", "correct horse battery staple")
    assert owner is not None and other is not None
    _library_entry(store, owner, "TEST-library-entry")
    service = PrivateDocumentService(store)
    uploaded = service.store_upload(
        user_id=owner,
        library_entry_id="TEST-library-entry",
        filename="..\\private\\draft.pdf",
        pdf_bytes=b"%PDF-TEST-private-document",
        rights_attested=True,
    )
    assert uploaded["state"] == "queued"
    assert uploaded["original_filename"] == "draft.pdf"
    assert "storage_key" not in uploaded

    monkeypatch.setattr(private_documents, "_parse_pdf_in_worker", _fake_parse)
    service.process_document(owner, uploaded["id"])
    indexed = service.get_document(owner, uploaded["id"])
    assert indexed is not None
    assert indexed["state"] == "indexed"
    assert indexed["parser_version"] == "mineru-4.1.test-papertrail-v8"
    assert indexed["chunker_version"] == "pdf-element-structure-token-upper-bound-v5"
    assert indexed["chunk_count"] == 3

    owned = service.search_evidence(
        "blue widgets", user_id=owner, source_type="arxiv", source_id="2401.12345", limit=5
    )
    hidden = service.search_evidence(
        "blue widgets", user_id=other, source_type="arxiv", source_id="2401.12345", limit=5
    )
    assert owned["status"] == "ok"
    assert owned["items"][0]["private_processing"] is True
    assert owned["items"][0]["excerpt"].startswith("TEST private evidence")
    assert hidden == {"status": "no_results", "items": [], "scanned_chunks": 0}
    assert (
        service.search_evidence(
            "tableonlyunitvalue",
            user_id=owner,
            source_type="arxiv",
            source_id="2401.12345",
            limit=5,
        )["status"]
        == "no_results"
    )
    assert (
        service.search_evidence(
            "figureonlycaptionvalue",
            user_id=owner,
            source_type="arxiv",
            source_id="2401.12345",
            limit=5,
        )["status"]
        == "no_results"
    )

    registry = PaperToolRegistry(store, user_id=owner)
    observation = registry.execute(
        "retrieve_paper_evidence",
        json.dumps(
            {
                "query": "blue widgets",
                "limit": 5,
                "source_type": "arxiv",
                "source_id": "2401.12345",
                "retrieval_method": "bm25",
            }
        ),
    )
    assert observation["status"] == "ok"
    assert observation["items"][0]["chunk_id"].startswith("private:")

    personal = service.store_upload(
        user_id=owner,
        title="TEST personal draft",
        filename="draft.pdf",
        pdf_bytes=b"%PDF-TEST-personal-separate",
        rights_attested=True,
    )
    service.process_document(owner, personal["id"])
    registry.library_only = True
    library_result = registry.execute(
        "retrieve_paper_evidence",
        json.dumps(
            {
                "query": "blue widgets",
                "limit": 5,
                "source_type": None,
                "source_id": None,
                "retrieval_method": "bm25",
            }
        ),
    )
    assert library_result["status"] == "ok"
    assert all(item["source_type"] == "arxiv" for item in library_result["items"])
    registry.library_only = False
    registry.account_documents_only = True
    mixed_library = registry.execute(
        "retrieve_paper_evidence",
        json.dumps(
            {
                "query": "blue widgets",
                "limit": 5,
                "source_type": None,
                "source_id": None,
                "retrieval_method": "bm25",
            }
        ),
    )
    mixed_draft = registry.execute(
        "retrieve_paper_evidence",
        json.dumps(
            {
                "query": "blue widgets",
                "limit": 5,
                "source_type": "personal",
                "source_id": None,
                "retrieval_method": "bm25",
            }
        ),
    )
    assert mixed_library["items"] and all(
        x["source_type"] == "arxiv" for x in mixed_library["items"]
    )
    assert mixed_draft["items"] and all(
        x["source_type"] == "personal" for x in mixed_draft["items"]
    )
    other_registry = PaperToolRegistry(store, user_id=other)
    other_registry.account_documents_only = True
    assert (
        other_registry.execute(
            "retrieve_paper_evidence",
            json.dumps(
                {
                    "query": "blue widgets",
                    "limit": 5,
                    "source_type": None,
                    "source_id": None,
                    "retrieval_method": "bm25",
                }
            ),
        )["items"]
        == []
    )
    service.delete_document(owner, personal["id"])

    class NoEmbeddings:
        def embed(self, *_args, **_kwargs):
            raise AssertionError("signed-in query reached embedding provider")

    registry = PaperToolRegistry(store, embeddings=NoEmbeddings(), user_id=owner)
    hybrid_arguments = json.dumps(
        {
            "query": "blue widgets",
            "limit": 5,
            "source_type": "arxiv",
            "source_id": "2401.12345",
            "retrieval_method": "hybrid",
        }
    )
    assert (
        registry.embedding_input_tokens_upper_bound("retrieve_paper_evidence", hybrid_arguments)
        == 0
    )
    assert registry.execute("retrieve_paper_evidence", hybrid_arguments)["status"] == "ok"

    with store._connection() as db:
        db.execute(
            "UPDATE user_documents SET parser_version='mineru-TEST-old' WHERE id=?",
            (uploaded["id"],),
        )
    assert service.pending_documents() == []
    assert service.get_document(owner, uploaded["id"])["error_code"] == "reindex_required"
    assert (
        service.search_evidence(
            "blue widgets", user_id=owner, source_type=None, source_id=None, limit=5
        )["status"]
        == "no_results"
    )

    assert service.retry_document(owner, uploaded["id"])
    service.process_document(owner, uploaded["id"])
    assert service.get_document(owner, uploaded["id"])["state"] == "indexed"

    path = service._path(owner, f"{uploaded['id']}.pdf")
    assert path.is_file()
    assert service.delete_document(owner, uploaded["id"]) == uploaded["id"]
    assert not path.exists()
    assert (
        service.search_evidence(
            "blue widgets", user_id=owner, source_type=None, source_id=None, limit=5
        )["status"]
        == "no_results"
    )

    def timed_out(_pdf_path: object) -> dict[str, object]:
        raise subprocess.TimeoutExpired("TEST-mineru-worker", 1)

    monkeypatch.setattr(private_documents, "_parse_pdf_in_worker", timed_out)
    timed_out_document = service.store_upload(
        user_id=owner,
        library_entry_id="TEST-library-entry",
        filename="timeout.pdf",
        pdf_bytes=b"%PDF-TEST-timeout",
        rights_attested=True,
    )
    service.process_document(owner, timed_out_document["id"])
    assert service.get_document(owner, timed_out_document["id"])["error_code"] == "mineru_timeout"
    service.delete_document(owner, timed_out_document["id"])

    def remote_config(_pdf_path: object) -> dict[str, object]:
        raise subprocess.CalledProcessError(3, "TEST-mineru-worker")

    monkeypatch.setattr(private_documents, "_parse_pdf_in_worker", remote_config)
    remote_document = service.store_upload(
        user_id=owner,
        library_entry_id="TEST-library-entry",
        filename="remote.pdf",
        pdf_bytes=b"%PDF-TEST-remote",
        rights_attested=True,
    )
    service.process_document(owner, remote_document["id"])
    assert (
        service.get_document(owner, remote_document["id"])["error_code"]
        == "mineru_remote_config_forbidden"
    )
    service.delete_document(owner, remote_document["id"])


def test_personal_document_private_retrieval_and_citation(tmp_path, monkeypatch) -> None:
    from app import private_documents
    from app.agent.tools import PaperToolRegistry

    store = PaperStore(tmp_path / "personal.sqlite3")
    owner = create_account(store, "personal_owner", "correct horse battery staple")
    other = create_account(store, "personal_other", "correct horse battery staple")
    assert owner and other
    service = PrivateDocumentService(store)
    uploaded = service.store_upload(
        user_id=owner,
        title="TEST unpublished draft",
        filename="draft.pdf",
        pdf_bytes=b"%PDF-TEST-personal",
        rights_attested=True,
    )
    assert uploaded["library_entry_id"] is None
    assert uploaded["source_type"] == "personal"
    assert uploaded["source_id"] == uploaded["id"]
    monkeypatch.setattr(private_documents, "_parse_pdf_in_worker", _fake_parse)
    service.process_document(owner, uploaded["id"])

    with store._connection() as db:
        db.execute(
            "UPDATE user_document_chunks SET locator=? WHERE document_id=?",
            ("Page 2 | " + "TEST long section heading " * 20, uploaded["id"]),
        )

    class NoSharedStore:
        def search_fulltext_evidence(self, *_args, **_kwargs):
            raise AssertionError("personal retrieval reached shared corpus")

    class NoEmbeddings:
        def embed(self, *_args, **_kwargs):
            raise AssertionError("personal retrieval reached embedding provider")

    arguments = json.dumps(
        {
            "query": "blue widgets",
            "limit": 5,
            "source_type": "personal",
            "source_id": uploaded["id"],
            "retrieval_method": "hybrid",
        }
    )
    registry = PaperToolRegistry(store, embeddings=NoEmbeddings(), user_id=owner)
    monkeypatch.setattr(store, "search_fulltext_evidence", NoSharedStore().search_fulltext_evidence)
    assert registry.embedding_input_tokens_upper_bound("retrieve_paper_evidence", arguments) == 0
    observation = registry.execute("retrieve_paper_evidence", arguments)
    assert observation["status"] == "ok"
    assert observation["retrieval_method"] == "private_bm25"
    item = observation["items"][0]
    assert item["personal_id"] == uploaded["id"]
    assert len(item["locator"]) == 240
    assert item["locator"].startswith("Page 2 | ")
    assert item["source_url"] == ""
    assert (
        PaperToolRegistry(store, user_id=other).execute(
            "retrieve_paper_evidence",
            arguments,
        )["items"]
        == []
    )
    citations, quotes = {}, {}
    _collect_citations(observation, citations, quotes)
    citation = citations[f"personal:{uploaded['id']}"]
    assert citation.personal_id == uploaded["id"]
    assert citation.source_url == ""
    assert quotes[f"personal:{uploaded['id']}"]
    from app.embeddings.client import EmbeddingBatch

    class TESTEmbeddings:
        model = "TEST-synthetic-embedding"

        def embed(self, texts):
            return EmbeddingBatch(self.model, [[1.0, 0.0] for _ in texts], len(texts))

    service.build_embeddings(owner, TESTEmbeddings())
    semantic = service.search_evidence(
        "TEST-unmatched-query",
        user_id=owner,
        source_type="personal",
        source_id=uploaded["id"],
        limit=5,
        query_vector=[1.0, 0.0],
        embedding_model=TESTEmbeddings.model,
    )
    assert semantic["retrieval_method"] == "private_hybrid_rrf"
    assert semantic["items"]
    assert not service.search_evidence(
        "TEST-unmatched-query",
        user_id=other,
        source_type="personal",
        source_id=uploaded["id"],
        limit=5,
        query_vector=[1.0, 0.0],
        embedding_model=TESTEmbeddings.model,
    )["items"]
    for changes in (
        {"private_processing": False},
        {"personal_id": "TEST-forged"},
        {"source_url": "https://example.test/forged"},
    ):
        forged = {**item, **changes}
        rejected, rejected_quotes = {}, {}
        _collect_citations({"items": [forged]}, rejected, rejected_quotes)
        assert not rejected
        assert not rejected_quotes

    forged_answer = json.dumps(
        {
            "answer": "TEST forged claim",
            "cited_openalex_ids": [],
            "cited_arxiv_ids": [],
            "cited_personal_ids": [uploaded["id"]],
            "claims": [],
            "insufficient_evidence": False,
        }
    )
    rejected_answer = AgentHarness._finalize(
        forged_answer,
        {},
        {},
        [],
        0,
        0,
        0,
        0,
    )
    assert rejected_answer.status == "unverified_citations"

    with store._connection() as db:
        db.execute(
            "UPDATE user_document_chunks SET retrieval_text=? WHERE document_id=?",
            ("TEST changed content", uploaded["id"]),
        )
    stale = service.search_evidence(
        "UNMATCHABLE",
        user_id=owner,
        source_type="personal",
        source_id=uploaded["id"],
        limit=5,
        query_vector=[1.0, 0.0],
        embedding_model=TESTEmbeddings.model,
    )
    assert stale["retrieval_method"] == "private_bm25"
    assert not stale["items"]

    service.delete_document(owner, uploaded["id"])
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM user_chunk_embeddings").fetchone()[0] == 0


def test_private_document_api_requires_attestation_and_enforces_ownership(
    tmp_path, monkeypatch
) -> None:
    from app import private_documents

    monkeypatch.setattr(private_documents, "_parse_pdf_in_worker", _fake_parse)
    settings = Settings(_env_file=None, data_storage_path=tmp_path / "api.sqlite3")
    app = create_app(settings)
    client_a = TestClient(app)
    client_b = TestClient(app)
    password = "correct horse battery staple"

    assert (
        client_a.post(
            "/api/v1/auth/register", json={"username": "doc_owner_a", "password": password}
        ).status_code
        == 201
    )
    assert (
        client_b.post(
            "/api/v1/auth/register", json={"username": "doc_owner_b", "password": password}
        ).status_code
        == 201
    )
    client_a.post("/api/v1/auth/login", json={"username": "doc_owner_a", "password": password})
    client_b.post("/api/v1/auth/login", json={"username": "doc_owner_b", "password": password})
    library = client_a.post(
        "/api/v1/library",
        json={
            "source": "arxiv",
            "source_id": "2401.12345",
            "metadata": {
                "id": "2401.12345",
                "sourceUrl": "https://arxiv.org/abs/2401.12345",
                "title": "TEST private paper",
            },
        },
    ).json()
    data = {"library_entry_id": library["id"], "rights_attested": "true"}
    refused = client_a.post(
        "/api/v1/documents",
        data={**data, "rights_attested": "false"},
        files={"file": ("paper.pdf", b"%PDF-TEST-private", "application/pdf")},
    )
    assert refused.status_code == 422
    assert client_a.get("/api/v1/documents").json() == []

    with TestClient(create_app(settings)) as worker_client:
        worker_client.post(
            "/api/v1/auth/login", json={"username": "doc_owner_a", "password": password}
        )
        uploaded = worker_client.post(
            "/api/v1/documents",
            data=data,
            files={"file": ("paper.pdf", b"%PDF-TEST-private", "application/pdf")},
        )
        assert uploaded.status_code == 202
        document_id = uploaded.json()["id"]
        assert uploaded.json()["rights_attested_at"]
        assert "storage_key" not in uploaded.json()
        assert client_b.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert client_b.get("/api/v1/documents").json() == []
        ambiguous = worker_client.post(
            "/api/v1/documents",
            data={**data, "title": "TEST ambiguous"},
            files={"file": ("ambiguous.pdf", b"%PDF-TEST-ambiguous", "application/pdf")},
        )
        assert ambiguous.status_code == 422
        personal = worker_client.post(
            "/api/v1/documents",
            data={"title": "TEST unpublished draft", "rights_attested": "true"},
            files={"file": ("personal.pdf", b"%PDF-TEST-personal-api", "application/pdf")},
        )
        assert personal.status_code == 202
        personal_id = personal.json()["id"]
        assert personal.json()["library_entry_id"] is None
        assert personal.json()["source_type"] == "personal"
        assert personal.json()["source_id"] == personal_id
        assert personal.json()["source_url"] == ""
        assert personal.json()["title"] == "TEST unpublished draft"
        assert worker_client.get("/api/v1/documents").json()[0]["source_url"] == ""
        assert client_b.get(f"/api/v1/documents/{personal_id}").status_code == 404
        assert worker_client.delete(f"/api/v1/documents/{personal_id}").status_code == 204
        assert worker_client.delete(f"/api/v1/library/{library['id']}").status_code == 409

        deadline = time.monotonic() + 5
        document = uploaded.json()
        while time.monotonic() < deadline and document["state"] not in {"indexed", "failed"}:
            time.sleep(0.02)
            document = worker_client.get(f"/api/v1/documents/{document_id}").json()
        assert document["state"] == "indexed"
        assert document["chunk_count"] == 3
        assert (
            worker_client.get(
                "/api/v1/documents", params={"library_entry_id": library["id"]}
            ).json()[0]["id"]
            == document_id
        )
        assert client_b.delete(f"/api/v1/documents/{document_id}").status_code == 404
        assert worker_client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert worker_client.delete(f"/api/v1/library/{library['id']}").status_code == 204
