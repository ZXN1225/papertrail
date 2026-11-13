"""Resolve explicit references only against the current account's indexed documents."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentTarget:
    source_type: str
    source_id: str
    title: str


_FOLLOWUP = re.compile(r"这篇|该论文|这份|该文|那篇|继续|进一步|this paper|that paper", re.I)
_MULTIPLE = re.compile(r"比较|对比|两篇|多篇|所有|全部|每篇|compare|all papers", re.I)
LOCAL_DOCUMENT_CUES = re.compile(
    r"入库|我的论文库|我的文献库|个人库|我的稿件|我上传|上传的论文|本地(?:论文|文稿|PDF)|"
    r"我(?:自己|本人)?的论文|我自己(?:的)?稿件|"
    r"my (?:own |uploaded |local |saved )?(?:paper|draft|manuscript)",
    re.I,
)
_LOCAL = LOCAL_DOCUMENT_CUES
_WEB = re.compile(r"联网|在线|网上|arxiv上|openalex上|on arxiv|on openalex", re.I)


def resolve_document(
    question: str, prior_questions: list[str], documents: list[DocumentTarget]
) -> tuple[DocumentTarget | None, bool]:
    """Return a unique target or signal ambiguity, never infer facts from model output."""

    def matches(text: str) -> list[DocumentTarget]:
        normalized = text.casefold()
        compact = re.sub(r"[^a-z0-9]", "", normalized)

        def title_matches(title: str) -> bool:
            title = title.strip().casefold()
            if len(title) >= 4 and title in normalized:
                return True
            compact_title = re.sub(r"[^a-z0-9]", "", title)
            return bool(len(compact_title) >= 6 and compact_title in compact)

        return [
            doc
            for doc in documents
            if title_matches(doc.title)
            or (
                len(doc.source_id) >= 4
                and re.search(
                    r"(?<![A-Za-z0-9.])" + re.escape(doc.source_id) + r"(?![A-Za-z0-9.])",
                    text,
                    re.I,
                )
            )
        ]

    if (
        _WEB.search(question)
        or _MULTIPLE.search(question)
        or (
            re.search(r"arxiv|openalex", question, re.I)
            and re.search(r"搜索|检索|查找|search|find", question, re.I)
        )
    ):
        return None, False
    current = matches(question)
    if len(current) == 1:
        return current[0], False
    if len(current) > 1:
        return None, True
    previous_local = False
    if _FOLLOWUP.search(question):
        for earlier in reversed(prior_questions):
            previous = matches(earlier)
            if len(previous) == 1:
                return previous[0], False
            if len(previous) > 1:
                return None, True
            if _LOCAL.search(earlier):
                previous_local = True
                break
            if not _FOLLOWUP.search(earlier):
                break
    if _LOCAL.search(question) or previous_local:
        scope = question if _LOCAL.search(question) else earlier
        candidates = documents
        if re.search(r"稿件|手稿|我(?:自己|本人)的论文|manuscript|draft", scope, re.I):
            candidates = [doc for doc in documents if doc.source_type == "personal"]
        elif re.search(r"论文库|文献库", scope):
            candidates = [doc for doc in documents if doc.source_type != "personal"]
        if len(candidates) == 1:
            return candidates[0], False
        if len(candidates) > 1:
            return None, True
    return None, False
