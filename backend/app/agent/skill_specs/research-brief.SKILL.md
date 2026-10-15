---
name: research-brief
description: Create a concise, evidence-linked research brief or literature overview.
version: 1.0.0
allowed-tools: search_papers,get_paper_details,retrieve_paper_evidence,find_related_papers,search_openalex_works,search_arxiv_metadata
---
# Evidence-linked research brief

Produce a bounded overview for the user's stated topic, audience, and time range.

1. Search for candidate papers, then retrieve evidence before describing their methods, findings, or limitations. Related-paper results are discovery leads, not proof of influence or relevance.
2. Organize the brief around a small number of themes or comparison dimensions requested by the user. Keep each paper's evidence separate before synthesizing across papers.
3. Attach citations and source locations to every factual claim. Distinguish reported results from cross-paper interpretation and mark disagreements or missing evidence.
4. State the scope of the retrieved corpus and its limits. Do not call a search exhaustive or systematic unless the workflow and coverage justify that claim.
5. End with open questions or evidence gaps when the available papers do not support a confident synthesis.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
