---
name: compare-papers
description: Compare selected papers while keeping metadata and findings distinct.
version: 1.0.0
allowed-tools: compare_papers,get_paper_details,retrieve_paper_evidence
---
# Compare papers

Compare two or more identified papers against the user's requested dimensions.

1. Confirm which papers are in scope. Use the structured comparison tool for bibliographic metadata; it does not establish similarity in methods or findings.
2. For each requested scientific dimension, retrieve evidence from each paper separately. Do not fill one paper's missing value from another paper or from model memory.
3. Keep study population, task, data, baselines, metrics, and experimental conditions attached to their source. Mark unavailable or non-comparable fields explicitly.
4. Cite each factual row or statement to evidence returned during this run. A paper-level citation without a supporting excerpt is not evidence for a methods or results claim.
5. Summarize similarities and differences only where the retrieved evidence supports them; avoid ranking papers unless the user supplied a defensible comparison criterion.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
