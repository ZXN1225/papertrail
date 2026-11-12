---
name: paper-qa
description: Answer a focused research question from traceable paper evidence.
version: 1.2.0
allowed-tools: get_paper_details,retrieve_paper_evidence,search_papers,search_arxiv_metadata,get_arxiv_metadata
---
# Paper question answering

Help the user answer one focused question about research papers.

## Prerequisites and scope

Restate the specific question and identify which paper or corpus is in scope. Clarify an ambiguous target before analysis. Metadata may locate candidate papers, but only suitable retrieved evidence can support claims about methods, findings, or limitations.

## Workflow and checkpoints

1. **Plan evidence needs:** break the question into answerable claims and identify the evidence type each needs.
2. **Retrieve:** use only registered PaperTrail tools. Prefer approved full text for methods/results/limitations; do not treat abstracts or search snippets as detailed findings.
3. **Check claims:** each factual statement must map to evidence returned in this run with source identity and locator. Separate reported findings from interpretation. Do not infer missing numbers, conditions, methods, licenses, or citations.
   MinerU visual descriptions are generated interpretations, not paper text; label them unverified, avoid presenting chart values as confirmed, and distinguish them from the exact caption.
4. **Stop or clarify:** if the target is unclear, the source is unavailable, or the evidence does not answer the question, state that limit and ask only the clarification needed; do not fill gaps from memory.
5. **Output check:** answer concisely, cite the supporting locations, and make the available corpus and unresolved gaps clear.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
