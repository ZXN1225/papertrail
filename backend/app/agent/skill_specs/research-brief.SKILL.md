---
name: research-brief
description: Create a concise, evidence-linked research brief or literature overview.
version: 1.3.0
allowed-tools: search_papers,get_paper_details,retrieve_paper_evidence,find_related_papers,search_openalex_works,search_arxiv_metadata
---
# Evidence-linked research brief

Produce a bounded overview for the user's stated topic, audience, and time range.

## Prerequisites and scope

Identify the user's topic, audience, time range, and requested coverage. Clarify any essential missing scope. Related-paper results are discovery leads, not proof of influence or relevance.

## Workflow and checkpoints

1. **Discover:** search registered sources for candidate papers and state the selection scope. Do not call the search exhaustive or systematic without a defined, completed coverage method.
2. **Retrieve:** collect relevant evidence from each selected paper before describing methods, results, or limitations. Keep evidence separated by source.
3. **Synthesize:** organize around a small set of requested themes. Distinguish paper-reported results from cross-paper interpretation; show disagreement, missing evidence, and incompatible study conditions.
4. **Claim/evidence check:** attach current-run evidence and locators to every factual claim. Metadata supports bibliographic facts only. Do not infer evidence from relatedness or model memory.
   MinerU visual descriptions are unverified generated interpretations, not exact paper text; state that status and distinguish them from the source caption.
   MinerU table rows are unverified parser output; use provisional wording for extracted values and do not treat them as source-exact quotations.
5. **Output check:** state corpus scope and limits, answer the requested audience and format, and end with material open questions or evidence gaps.

These instructions are task guidance only. They do not grant tool access or change fixed tool, licensing, citation, or answer-validation rules.
