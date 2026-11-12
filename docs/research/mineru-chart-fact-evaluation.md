# MinerU Chart Fact Evaluation

## Scope and status

This is an offline protocol for reviewing MinerU chart answers and page-level chart detection against a frozen, rights-attested source set. It complements the existing page/element parse review packet with query-level facts and deterministic scoring. It does not claim chart accuracy by itself; reports always carry `gold_standard=false` and `quality_claim_allowed=false`.

The first protocol version accepts only local chart-task JSON and local page-image references. It makes no provider calls and does not read or write SQLite. Human reviewers inspect the referenced source page and complete each task. A task may be `answerable`, `unanswerable`, or `uncertain`; uncertain rows remain visible in the audit but are excluded from scoring.

## Fact labels

Supported fact buckets are `axis_label`, `series_label`, `numeric_value`, `trend`, and `comparison`. Numeric reference facts include a unit and non-negative absolute tolerance. Categorical facts are normalized for case and whitespace; numeric values are matched one-to-one within their reviewed tolerance and with matching units. The report includes micro precision, recall, F1, per-bucket scores, and abstention accuracy. A separate page-audit pack records a human-reviewed or uncertain reference chart count for each sampled page; the manifest must include at least one test page with zero predicted charts. It reports chart-count precision/recall/F1, exact page-count accuracy, and pages where the parser predicted no chart despite a reviewed chart being present.

Tasks bind to the source PDF SHA-256, parser report SHA-256, parser version, page image SHA-256, page number, element ID, and bounding box. Page image references must be relative to the dataset folder and are hash-checked at export and import. The `rights_attested` flag and PDF/parser-report hashes are operator-provided provenance declarations; this CLI does not open those files to independently confirm their contents or licensing. All pages from one source must share a `dev` or `test` split; duplicate PDF hashes also cannot cross splits. Test scores only use the held-out test split. The page-presence audit is the mechanism for estimating missed figures; its page sample must include pages with zero predicted figures, or recall is not measurable. Count metrics score the number of chart regions per page; they do not score region localization overlap or figure-to-caption association quality.

## Local workflow

From `backend/`, prepare a local dataset with schema `papertrail.mineru-chart-tasks.v1`. Use `gold_standard: false`, `quality_claim_allowed: false`, source metadata limited to `pdf_sha256`, `parse_report_sha256`, `parser_version`, and `rights_attested: true`, plus chart-question tasks and `page_audits` for a documented page sample. Synthetic field examples are in `tests/test_mineru_chart_review.py`.

```powershell
uv run --locked python -m app.cli.review_mineru_charts export `
  --dataset reports/live_eval/mineru/TEST-chart-tasks.json `
  --output reports/live_eval/mineru/TEST-chart-review-pack.json
```

Review the page image and MinerU output independently, enter the reference fact list and `reference_status` for every task, and then import to a new file. The explicit confirmation is an assertion that a human completed the review; it cannot be supplied by an AI-generated candidate label.

```powershell
uv run --locked python -m app.cli.review_mineru_charts import `
  --dataset reports/live_eval/mineru/TEST-chart-tasks.json `
  --pack reports/live_eval/mineru/TEST-chart-review-pack.json `
  --output reports/live_eval/mineru/TEST-chart-reviewed.json `
  --reviewer "reviewer-id" --confirm-human-review

uv run --locked python -m app.cli.review_mineru_charts evaluate `
  --dataset reports/live_eval/mineru/TEST-chart-reviewed.json `
  --output reports/live_eval/mineru/TEST-chart-evaluation.json
```

All outputs should remain in ignored local review directories. Export/import refuse to overwrite existing files and verify task/source/image provenance. The reviewed dataset stores the source dataset hash, review-pack hash, and a digest over all scored content; evaluation rejects edits after import. These hashes detect accidental drift but are not digital signatures against a malicious editor. Review labels are still single-reviewer labels unless a future adjudication protocol records multiple independent reviewers; they must not be described as a gold standard. LLM-as-judge can provide a separate, budgeted diagnostic, but it cannot change the human reference labels or lift the report quality gate.

## Verification boundary

Current automated fixtures use `TEST-*` synthetic tasks and verify exact categorical matches, numeric tolerance, one-to-one fact matching, abstention, uncertain rows, document-level split isolation, rights/provenance validation, and output overwrite/image hash guards. They validate evaluator mechanics only. Real MinerU chart-fact accuracy remains unmeasured until a rights-attested, independently human-reviewed, held-out set is prepared and evaluated. No provider transfer is part of this CLI.

## Optional LLM-as-judge diagnostic

The separate `app.cli.run_mineru_chart_judge` command consumes the imported human-reviewed dataset and judges only adjudicated test tasks. It asks a different model to match predicted fact indices to human reference fact IDs and score semantic relevance/faithfulness; the shared 1/3/5 rubric anchors unrelated/partial/direct relevance and mostly unsupported/mixed/fully supported facts. It never changes reference labels. It is a secondary diagnostic beside deterministic exact/tolerance-aware scoring, not a source of gold labels. Each judge input is capped at 20,000 characters and all selected inputs are checked before the first provider call.

Dry-run first. It reports the task count, a zero-call budget preflight, and the conservative full-run token/cost reservation without writing an output report. An execute run is rejected before creating a report or opening the provider if the estimated complete run exceeds the cost cap. During execution, each request is still checked against the remaining local budget; provider usage/pricing can differ from the estimate, so the cap is not provider-enforced. If a live run is explicitly authorized, it sends only the task question, candidate facts, abstention status, and human reference facts. These JSON values are treated as untrusted data by the judge prompt. It does not send page images, PDFs, parser reports, or whole paper text. Because the human reference facts and chart question are still externally transmitted, every live invocation requires `--confirm-data-transfer`, a non-synthetic reviewed dataset, a different candidate/judge model, and explicit per-million prices, call cap, and estimated-cost cap. This CLI does not run a live judge as part of CI or this implementation.

```powershell
uv run --locked python -m app.cli.run_mineru_chart_judge `
  --dataset reports/live_eval/mineru/TEST-chart-reviewed.json `
  --output reports/live_eval/mineru/TEST-chart-llm-judge.json `
  --candidate-model "candidate-model-id" --judge-model "different-judge-model-id" `
  --max-tasks 20 --max-provider-calls 20 --max-cost-usd 0.25 `
  --input-price-per-million-usd 1 --output-price-per-million-usd 5

# After checking the dry-run details and authorizing the listed data transfer:
uv run --locked python -m app.cli.run_mineru_chart_judge `
  --dataset reports/live_eval/mineru/TEST-chart-reviewed.json `
  --output reports/live_eval/mineru/TEST-chart-llm-judge.json `
  --candidate-model "candidate-model-id" --judge-model "different-judge-model-id" `
  --max-tasks 20 --max-provider-calls 20 --max-cost-usd 0.25 `
  --input-price-per-million-usd 1 --output-price-per-million-usd 5 `
  --execute --confirm-data-transfer
```

The report carries the prompt version, dataset/review-pack hashes, model IDs, token/cost estimates, task-level structured verdicts, and unconditional `quality_claim_allowed=false`. Keep reports in ignored local directories; judge rationales may contain user-provided chart wording.
