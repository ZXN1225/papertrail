---
name: paper-qa
description: Answer a focused research question from traceable paper evidence.
version: 1.0.0
allowed-tools: get_paper_details,retrieve_paper_evidence,search_papers,search_arxiv_metadata,get_arxiv_metadata
---
# Paper question answering

Help the user answer one focused question about research papers.

1. Restate the exact question internally and identify which claims need evidence.
2. Search only the registered PaperTrail tools. Prefer approved full-text evidence for claims about methods, results, and limitations; metadata search may find candidate papers but does not establish their findings.
3. Ground each factual claim in evidence returned during this run. Preserve the paper ID and source location supplied by the tool. If evidence does not support a claim, omit it or label the gap clearly.
4. Distinguish what a paper reports from what can be concluded across papers. Do not infer missing numbers, methods, licenses, or citations.
5. Give a concise answer, followed by the relevant papers and evidence locations. State when the available material is insufficient.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
