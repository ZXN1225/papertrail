---
name: compare-papers
description: Compare selected papers while keeping metadata and findings distinct.
version: 1.2.0
allowed-tools: compare_papers,get_paper_details,retrieve_paper_evidence
---
# Compare papers

Compare two or more identified papers against the user's requested dimensions.

## Prerequisites and scope

Confirm the requested papers and comparison dimensions. Bibliographic metadata can identify papers but cannot establish method or result similarity. Ask which papers or dimensions the user means when they are ambiguous; do not silently choose a comparison set.

## Workflow and checkpoints

1. **Identify:** use the registered metadata comparison to confirm source identity and requested set. Stop if fewer than two papers are identified.
2. **Retrieve separately:** for every paper and requested dimension, retrieve that paper's evidence. A missing result in one paper must remain missing; do not transfer another paper's value or use model memory.
3. **Build a source-by-dimension matrix:** rows are papers; columns are the requested dimensions. For each cell record `evidence`, `not found in retrieved passages`, `not comparable`, or `source unavailable`, plus its source locator when evidence exists. Keep population, task, data, baseline, metric, condition, and timepoint attached to the source.
4. **Synthesize:** report similarities or differences only when the corresponding cells support them. Do not rank papers unless the user supplied a defensible criterion. A paper citation without a relevant excerpt does not support a finding.
   If a cell uses a MinerU table row, mark it as unverified parser output; do not claim an exact numeric comparison until the source page confirms both values.
5. **Output check:** ensure every factual cell and synthesis claim maps to current-run evidence, label non-comparable or unavailable cells, and state retrieval limits. Never present a partial matrix as exhaustive coverage.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
