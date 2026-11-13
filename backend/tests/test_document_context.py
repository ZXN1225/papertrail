import pytest

from app.agent.document_context import DocumentTarget, resolve_document
from app.agent.tasks import prepare_task


@pytest.mark.parametrize(
    "question",
    [
        "根据已经入库的我自己的论文，请你解释论文立意，分析证据，并做出评价",
        "请分析入库的我本人论文",
        "评价我自己的论文",
    ],
)
def test_local_paraphrases_never_select_generic_online_task(question):
    assert prepare_task(question).spec.task_id == "personal-paper-qa"
    doc = DocumentTarget("personal", "11111111-1111-1111-1111-111111111111", "TEST draft")
    assert resolve_document(question, [], [doc]) == (doc, False)


def test_explicit_target_and_followup_are_resolved_without_guessing() -> None:
    docs = [
        DocumentTarget("personal", "11111111-1111-1111-1111-111111111111", "Master Thesis"),
        DocumentTarget("arxiv", "2511.22858", "TEST Library Paper"),
    ]
    first, ambiguous = resolve_document("总结 Master Thesis", [], docs)
    assert first == docs[0] and not ambiguous
    target, ambiguous = resolve_document("评价这篇论文", ["总结 Master Thesis"], docs)
    assert target == docs[0] and not ambiguous
    assert (
        prepare_task("评价这篇论文", target_source_type=target.source_type).spec.task_id
        == "personal-paper-qa"
    )
    assert resolve_document("根据我已入库的论文总结立意", [], docs) == (None, True)
    assert resolve_document("分析我的稿件", [], docs) == (docs[0], False)
    assert resolve_document("搜索 arxiv 中的 Master Thesis", [], docs) == (None, False)
    assert resolve_document("比较我的论文库中两篇论文", [], docs) == (None, False)
    assert resolve_document("总结 2511.22858", ["总结 Master Thesis"], docs) == (docs[1], False)
    assert resolve_document("总结 MasterThesis", [], docs) == (docs[0], False)
    assert resolve_document("评价这篇论文", ["总结 Master Thesis"] + ["继续分析"] * 12, docs) == (
        docs[0],
        False,
    )
    assert resolve_document("分析 2511.228589", [], docs) == (None, False)
    assert resolve_document("评价这篇论文", ["总结 Master Thesis", "搜索别的主题"], docs) == (
        None,
        False,
    )


def test_account_target_rejects_conflicting_model_source() -> None:
    from app.agent.contracts import RetrieveEvidenceArgs
    from app.agent.tools import PaperToolRegistry

    registry = PaperToolRegistry(None, user_id="TEST-owner")  # type: ignore[arg-type]
    registry.document_target = ("personal", "11111111-1111-1111-1111-111111111111")
    args = RetrieveEvidenceArgs(
        query="TEST", limit=3, source_type="arxiv", source_id="2511.22858", retrieval_method="bm25"
    )
    assert registry._retrieve_evidence(args) == {
        "status": "error",
        "code": "document_target_mismatch",
    }


def test_account_target_injects_exact_source_into_private_search(monkeypatch) -> None:
    from app.agent.contracts import RetrieveEvidenceArgs
    from app.agent.tools import PaperToolRegistry

    observed = {}

    class FakeDocuments:
        def __init__(self, store):
            pass

        def search_evidence(self, query, **kwargs):
            observed.update(kwargs)
            return {"status": "no_results", "items": []}

    monkeypatch.setattr("app.agent.tools.PrivateDocumentService", FakeDocuments)
    registry = PaperToolRegistry(None, user_id="TEST-owner")  # type: ignore[arg-type]
    registry.account_documents_only = True
    registry.document_target = ("personal", "11111111-1111-1111-1111-111111111111")
    args = RetrieveEvidenceArgs(query="TEST", limit=3, retrieval_method="bm25")
    registry._retrieve_evidence(args)
    assert observed["user_id"] == "TEST-owner"
    assert (observed["source_type"], observed["source_id"]) == registry.document_target


def test_library_only_rejects_personal_scope() -> None:
    from app.agent.contracts import RetrieveEvidenceArgs
    from app.agent.tools import PaperToolRegistry

    registry = PaperToolRegistry(None, user_id="TEST-owner")  # type: ignore[arg-type]
    registry.library_only = True
    args = RetrieveEvidenceArgs(
        query="TEST", limit=3, source_type="personal", retrieval_method="bm25"
    )
    assert registry._retrieve_evidence(args) == {
        "status": "error",
        "code": "library_scope_requires_nonpersonal_source",
    }
