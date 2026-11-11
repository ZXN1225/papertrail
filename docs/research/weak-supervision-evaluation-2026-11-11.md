# Weak-supervision retrieval diagnostics

This tool builds a reproducible retrieval diagnostic from the current approved full-text index. It only includes `arxiv` and `openalex` full-text rows with an allowlisted CC0 or CC-BY license, and records the active content, source-document, parser, chunker, and license lineage. It uses a read-only store and refuses to overwrite an existing output.

```powershell
cd backend
uv run --locked python -m app.cli.build_weak_supervision_dataset `
  --source-type arxiv `
  --output reports/weak-supervision-arxiv-v1.json
uv run --locked python -m app.cli.evaluate_weak_supervision `
  --dataset reports/weak-supervision-arxiv-v1.json `
  --split test `
  --k 5 `
  --output reports/weak-supervision-arxiv-test-v1.json
```

Queries are formed from the longest sentence in a source chunk by masking one term. The source chunk is the sole weak relevance reference. The source grouping keeps a paper in one train/dev/test split; small corpora may leave one or more splits empty, which the manifest reports and the runner rejects when selected. `--split all` can be used for a descriptive smoke run, not held-out evaluation.

The report contains Hit, standard fixed-denominator Precision@k, returned-set precision, Recall, MRR and nDCG at `k`, grouped by query bucket, plus retrieval latency. The answer term and source text share provenance, so lexical overlap is expected. This measures a narrow masked-term retrieval behavior only; it is not a set of natural user questions, semantic qrels, answer-grounding accuracy, or a gold benchmark. Do not use it to make general quality claims. A separately generated task set, human-reviewed calibration sample, and LLM-as-judge protocol remain outstanding.
