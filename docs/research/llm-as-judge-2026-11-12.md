# LLM-as-judge diagnostic v1

## What it evaluates

The runner evaluates a frozen answer bundle against a frozen task dataset and the current read-only PaperTrail index. It rates answer relevance, support from cited evidence, citation quality, and abstention appropriateness. It reports per-answer rows, cohort means, unsupported-claim counts, latency, and provider-call accounting.

This is an **uncalibrated AI diagnostic**. The report always sets `gold_standard`, `human_reviewed`, and `quality_claim_allowed` to false. Scores must not be presented as accuracy, human labels, or a gold benchmark. A separate human-reviewed anchor set and judge calibration remain future work.

## Safety and lineage

- The CLI defaults to a dry run and makes zero provider calls.
- Live judging requires both `--execute` and `--confirm-data-transfer`; synthetic datasets are rejected for live calls.
- The PaperStore is opened read-only. Every source must still match the dataset's approved CC-BY-4.0 license, license URL, full-text SHA-256, source-document SHA-256, and parser version.
- Each cited chunk must belong to the task's exact source and current content hash. Only those excerpts (maximum five, 1,200 characters each) are sent with the question and answer (maximum 4,000 characters). The judge receives no tools and cannot browse or write data.
- Evidence IDs are shuffled and aliased; cohort IDs and candidate model identity are not in the judge prompt. A different declared model name is required, but provider/account independence is not proven.
- The local call and estimated-cost budget blocks additional calls and stops on provider failure or unknown usage. The estimate is not a provider-side billing cap.

## CLI

Run preflight without a model call:

```powershell
cd backend
uv run --locked python -m app.cli.run_llm_judge `
  --dataset data/evaluation/ai-labeled-tasks.json `
  --answers data/evaluation/answer-bundle.json `
  --output reports/live_eval/llm-judge.json `
  --judge-model <independent-model-name> `
  --max-cost-usd 1.00 `
  --input-price-per-million-usd <input-price> `
  --output-price-per-million-usd <output-price>
```

Live execution additionally requires `--execute --confirm-data-transfer`, a configured `LLM_API_KEY`, a non-synthetic dataset, and explicit price/call limits. Use only when the cited source's license and the provider's data-handling terms permit the transfer. Reports are created exclusively; choose a new output path for every run.

## Report interpretation

`status` is `completed` only when every answer has a valid structured judgment. A provider error records the failed attempt as `unavailable`; remaining rows are `not_judged`. `budget.provider_calls` counts attempted requests (including failed requests), while `successful_provider_calls` counts responses received. Invalid output is unavailable, not a zero score.

## Verification

The synthetic fixtures use `TEST-*` identifiers and make no provider calls. The live path was not executed in development. See the PR checks and backend tests for the verified behavior.
