"""Compare BM25 with true candidate-text vector reranking on a frozen approved corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.config import get_settings
from app.embeddings.client import (
    MAX_BATCH_SIZE,
    MAX_INPUT_CHARS,
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.evaluation.chunking import (
    STRATEGIES,
    _bm25_documents,
    _retrieval_metrics,
    _span_is_covered,
    run_evaluation,
)
from app.evaluation.fulltext_retrieval import DEFAULT_DATASET_PATH, load_dataset
from app.retrieval.bm25 import BM25Index
from app.retrieval.fulltext import chunk_pdf_elements
from app.retrieval.vectors import cosine_similarity
from app.storage.repository import PaperStore

LOCAL_CACHE_ROOT = Path(__file__).resolve().parents[1] / ".local" / "candidate-rerank-cache"
SHORTLIST_LIMIT = 128


def _positive_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("--max-cost-usd must be a positive decimal") from error
    if not number.is_finite() or number <= 0:
        raise ValueError("--max-cost-usd must be a positive decimal")
    return number


class BatchCache:
    """Ignored local cache; each provider attempt reserves its byte-based cost first."""

    def __init__(self, path: Path, plan_sha: str, model: str, dimensions: int) -> None:
        self.path = path
        self.plan_sha = plan_sha
        self.model = model
        self.dimensions = dimensions

    def _header(self) -> dict[str, object]:
        return {
            "plan_sha256": self.plan_sha,
            "model": self.model,
            "dimensions": self.dimensions,
        }

    def _validate_header(self) -> None:
        header_path = self.path / "header.json"
        if not self.path.exists():
            return
        if (
            not header_path.exists()
            or json.loads(header_path.read_text(encoding="utf-8")) != self._header()
        ):
            raise ValueError("candidate embedding cache header does not match this plan")

    def initialize(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        header_path = self.path / "header.json"
        if not header_path.exists():
            with header_path.open("x", encoding="utf-8") as stream:
                json.dump(self._header(), stream, sort_keys=True)
        self._validate_header()

    def _batch_key(self, texts: list[str]) -> tuple[str, list[str]]:
        text_hashes = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
        key = hashlib.sha256(json.dumps(text_hashes, separators=(",", ":")).encode()).hexdigest()
        return key, text_hashes

    def _read_batch(self, texts: list[str]) -> tuple[list[list[float]], int] | None:
        key, text_hashes = self._batch_key(texts)
        path = self.path / f"{key}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        vectors = payload.get("vectors")
        tokens = payload.get("input_tokens")
        if (
            payload.get("plan_sha256") != self.plan_sha
            or payload.get("text_sha256") != text_hashes
            or type(tokens) is not int
            or tokens < 0
            or not isinstance(vectors, list)
            or len(vectors) != len(texts)
            or any(
                not isinstance(vector, list)
                or len(vector) != self.dimensions
                or any(
                    type(value) not in (int, float) or not math.isfinite(value) for value in vector
                )
                for vector in vectors
            )
        ):
            raise ValueError("candidate embedding cache batch is invalid")
        return vectors, tokens

    def _attempted_bytes(self) -> int:
        path = self.path / "attempts.jsonl"
        if not path.exists():
            return 0
        total = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if (
                record.get("plan_sha256") != self.plan_sha
                or not isinstance(record.get("batch_sha256"), str)
                or type(record.get("input_utf8_bytes")) is not int
                or record["input_utf8_bytes"] < 1
            ):
                raise ValueError("candidate embedding cache attempt ledger is invalid")
            total += record["input_utf8_bytes"]
        return total

    def inspect(self, batches: list[list[str]], price: Decimal) -> dict[str, object]:
        self._validate_header()
        cached = 0
        missing_bytes = 0
        for texts in batches:
            if self._read_batch(texts) is None:
                missing_bytes += sum(len(text.encode("utf-8")) for text in texts)
            else:
                cached += 1
        attempted_bytes = self._attempted_bytes()
        return {
            "cached_batch_count": cached,
            "remaining_batch_count": len(batches) - cached,
            "attempted_utf8_bytes_reserved": attempted_bytes,
            "estimated_cumulative_upper_bound_cost_usd": str(
                price * Decimal(attempted_bytes + missing_bytes) / Decimal(1_000_000)
            ),
        }

    def get_or_embed(
        self,
        texts: list[str],
        client: OpenAIEmbeddingClient,
        price: Decimal,
        max_cost: Decimal,
    ) -> tuple[list[list[float]], int, bool]:
        self._validate_header()
        cached = self._read_batch(texts)
        if cached is not None:
            return cached[0], cached[1], False
        self.initialize()
        batch_bytes = sum(len(text.encode("utf-8")) for text in texts)
        if price * Decimal(self._attempted_bytes() + batch_bytes) / Decimal(1_000_000) > max_cost:
            raise ValueError("cumulative embedding attempt estimate exceeds --max-cost-usd")
        key, text_hashes = self._batch_key(texts)
        with (self.path / "attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "plan_sha256": self.plan_sha,
                        "batch_sha256": key,
                        "input_utf8_bytes": batch_bytes,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        batch = client.embed(texts)
        if batch.model != self.model or any(
            len(vector) != self.dimensions for vector in batch.vectors
        ):
            raise ValueError("embedding provider model or dimension mismatch")
        payload = {
            "plan_sha256": self.plan_sha,
            "text_sha256": text_hashes,
            "vectors": batch.vectors,
            "input_tokens": batch.input_tokens,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.path, prefix="batch-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temp_path, self.path / f"{key}.json")
        finally:
            temp_path.unlink(missing_ok=True)
        return batch.vectors, batch.input_tokens, True


def _select_shortlists(
    candidates: list[dict[str, object]], dataset: dict[str, object]
) -> tuple[dict[str, list[str]], dict[str, dict[str, object]]]:
    by_id = {str(candidate["chunk_id"]): candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate IDs are not unique")
    source_scope = dataset.get("source_scope", "exact_arxiv_id_per_task")
    if source_scope == "all_approved_arxiv":
        indexes = {"all": BM25Index(_bm25_documents(candidates))}
    else:
        indexes = {
            source_id: BM25Index(
                _bm25_documents([item for item in candidates if item["source_id"] == source_id])
            )
            for source_id in dataset["sources"]
        }
    selected: dict[str, dict[str, object]] = {}
    hits_by_task: dict[str, list[str]] = {}
    for task in dataset["tasks"]:
        index = indexes["all" if source_scope == "all_approved_arxiv" else task["source_id"]]
        hit_ids = [hit.openalex_id for hit in index.search(task["question"], limit=SHORTLIST_LIMIT)]
        hits_by_task[task["task_id"]] = hit_ids
        selected.update({hit_id: by_id[hit_id] for hit_id in hit_ids})
    return hits_by_task, selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-data-transfer", action="store_true")
    parser.add_argument("--max-query-embeddings", type=int, required=True)
    parser.add_argument("--max-new-texts", type=int, required=True)
    parser.add_argument("--max-new-utf8-bytes", type=int, required=True)
    parser.add_argument("--max-cost-usd", required=True)
    args = parser.parse_args(argv)

    if args.execute and not args.confirm_data_transfer:
        parser.error("--execute requires --confirm-data-transfer")
    output = args.output.resolve()
    if args.execute and output.exists():
        parser.error("refusing to overwrite existing diagnostic")

    settings = get_settings()
    if (
        not settings.embedding_model
        or not settings.embedding_dimensions
        or settings.embedding_price_per_million_usd is None
        or settings.embedding_price_per_million_usd <= 0
    ):
        raise ValueError("a priced embedding model and dimensions are required")
    if args.execute and settings.embedding_provider != "openai":
        raise ValueError("live evaluation requires embedding provider=openai")
    price = Decimal(str(settings.embedding_price_per_million_usd))
    max_cost = _positive_decimal(args.max_cost_usd)
    dataset, dataset_sha = load_dataset(args.dataset)
    if args.max_query_embeddings < len(dataset["tasks"]):
        raise ValueError("--max-query-embeddings must cover every task")
    if args.max_new_texts < 1 or args.max_new_utf8_bytes < 1:
        raise ValueError("new-text count and byte caps must be positive")
    store = PaperStore(settings.resolved_data_storage_path, readonly=True)
    baseline = run_evaluation(store, dataset, dataset_sha)
    if baseline["dataset"]["quality_claim_allowed"] is not False:
        raise ValueError("only exploratory diagnostics are permitted")

    parent_vectors_by_text = {}
    elements_by_source = {}
    metadata_by_source = {}
    for source_id in dataset["sources"]:
        metadata_by_source[source_id] = store.get_current_fulltext_metadata(
            source_type="arxiv", source_id=source_id
        )
        elements_by_source[source_id] = store.list_current_fulltext_elements(
            source_type="arxiv", source_id=source_id
        )
        parent_chunks = store.list_current_fulltext_chunks(source_type="arxiv", source_id=source_id)
        vectors = store.list_current_fulltext_embeddings(
            source_type="arxiv",
            source_ids=[source_id],
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        if len(vectors) != len(parent_chunks) or any(vector is None for vector in vectors.values()):
            raise ValueError("current parent index is incomplete")
        for parent in parent_chunks:
            parent_vectors_by_text.setdefault(parent["text"], vectors[parent["chunk_id"]])

    arms = {}
    selected = {}
    for strategy, (max_bytes, overlap_bytes) in STRATEGIES.items():
        candidates = []
        for source_id, elements in elements_by_source.items():
            for chunk in chunk_pdf_elements(
                elements, max_chunk_bytes=max_bytes, max_overlap_bytes=overlap_bytes
            ):
                candidates.append(
                    {
                        "chunk_id": f"{strategy}:{source_id}:{chunk.element_id}:{chunk.ordinal}",
                        "source_id": source_id,
                        "title": metadata_by_source[source_id]["title"],
                        "text": chunk.text,
                        "section_path": chunk.section_path,
                        "element_id": chunk.element_id,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                    }
                )
        by_id = {candidate["chunk_id"]: candidate for candidate in candidates}
        source_scope = dataset.get("source_scope", "exact_arxiv_id_per_task")
        hits_by_task, selected_for_arm = _select_shortlists(candidates, dataset)
        selected.update(selected_for_arm)
        arms[strategy] = (candidates, by_id, hits_by_task)

    new_texts = {candidate["text"] for candidate in selected.values()}
    new_texts.difference_update(parent_vectors_by_text)
    new_bytes = sum(len(text.encode("utf-8")) for text in new_texts)
    question_bytes = sum(len(task["question"].encode("utf-8")) for task in dataset["tasks"])
    if (
        len(new_texts) > args.max_new_texts
        or new_bytes > args.max_new_utf8_bytes
        or any(not text.strip() or len(text) > MAX_INPUT_CHARS for text in new_texts)
        or any(
            not task["question"].strip() or len(task["question"]) > MAX_INPUT_CHARS
            for task in dataset["tasks"]
        )
    ):
        raise ValueError("candidate transfer scope exceeds explicit count, byte, or input limits")
    upper_cost = price * Decimal(new_bytes + question_bytes) / Decimal(1_000_000)
    if upper_cost > max_cost:
        raise ValueError("estimated transfer cost exceeds authorized cap")
    ordered_texts = sorted(new_texts, key=lambda text: hashlib.sha256(text.encode()).hexdigest())
    batches = [[task["question"] for task in dataset["tasks"]]]
    batches.extend(
        ordered_texts[start : start + MAX_BATCH_SIZE]
        for start in range(0, len(ordered_texts), MAX_BATCH_SIZE)
    )
    plan_sha = hashlib.sha256(
        json.dumps(
            {
                "dataset_sha256": dataset_sha,
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "source_scope": source_scope,
                "candidate_text_sha256": [
                    hashlib.sha256(text.encode()).hexdigest() for text in ordered_texts
                ],
                "question_sha256": [
                    hashlib.sha256(text.encode()).hexdigest() for text in batches[0]
                ],
                "strategies": STRATEGIES,
                "shortlist_limit": SHORTLIST_LIMIT,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    cache = BatchCache(
        LOCAL_CACHE_ROOT / plan_sha,
        plan_sha,
        settings.embedding_model,
        settings.embedding_dimensions,
    )
    cache_status = cache.inspect(batches, price)
    scope = {
        "dataset_sha256": dataset_sha,
        "source_scope": source_scope,
        "plan_sha256": plan_sha,
        "source_count": len(dataset["sources"]),
        "task_count": len(dataset["tasks"]),
        "selected_candidate_ids": len(selected),
        "new_unique_texts": len(new_texts),
        "new_utf8_bytes_upper_bound": new_bytes,
        "question_utf8_bytes_upper_bound": question_bytes,
        "provider_call_upper_bound": len(batches),
        "estimated_upper_bound_cost_usd": str(upper_cost),
        "max_cost_usd": str(max_cost),
        "model": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        **cache_status,
        "gold_standard": False,
        "quality_claim_allowed": False,
    }
    if not args.execute:
        print(
            json.dumps({"status": "dry_run_passed", "provider_calls": 0, **scope}, sort_keys=True)
        )
        return 0
    if Decimal(str(cache_status["estimated_cumulative_upper_bound_cost_usd"])) > max_cost:
        raise ValueError("cached attempts plus remaining transfer exceed --max-cost-usd")

    vectors_by_text = dict(parent_vectors_by_text)
    tokens_new = 0
    calls_new = 0
    cache.initialize()
    lock_path = cache.path / "run.lock"
    with lock_path.open("x", encoding="utf-8") as lock:
        lock.write("single local evaluator process\n")
    try:
        client = OpenAIEmbeddingClient(settings)
        try:
            for batch_index, texts in enumerate(batches):
                vectors, input_tokens, called = cache.get_or_embed(texts, client, price, max_cost)
                tokens_new += input_tokens if called else 0
                calls_new += int(called)
                if batch_index == 0:
                    query_vectors_list = vectors
                else:
                    vectors_by_text.update(zip(texts, vectors, strict=True))
            query_vectors = dict(
                zip((task["task_id"] for task in dataset["tasks"]), query_vectors_list, strict=True)
            )
        finally:
            client.close()
    finally:
        lock_path.unlink(missing_ok=True)

    report_arms = {}
    for strategy, (candidates, by_id, hits_by_task) in arms.items():
        rows = []
        for task, baseline_task in zip(
            dataset["tasks"], baseline["strategies"][strategy]["tasks"], strict=True
        ):
            anchor_start, anchor_end = baseline_task["reference_span"]
            element_id = baseline_task["reference_element_id"]
            relevant = {
                candidate["chunk_id"]: 1
                for candidate in candidates
                if candidate["source_id"] == task["source_id"]
                and candidate["element_id"] == element_id
                and candidate["char_start"] < anchor_end
                and candidate["char_end"] > anchor_start
            }
            source_element = next(
                element
                for element in elements_by_source[task["source_id"]]
                if element["element_id"] == element_id
            )
            started = time.perf_counter_ns()
            hit_ids = hits_by_task[task["task_id"]]
            bm25_rank = {hit_id: rank for rank, hit_id in enumerate(hit_ids)}
            ranking = sorted(
                hit_ids,
                key=lambda hit_id: (
                    -cosine_similarity(
                        query_vectors[task["task_id"]], vectors_by_text[by_id[hit_id]["text"]]
                    ),
                    bm25_rank[hit_id],
                ),
            )[: dataset["top_k"]]
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            cutoffs = tuple(
                sorted({1, min(3, dataset["top_k"]), min(5, dataset["top_k"]), dataset["top_k"]})
            )
            metrics = _retrieval_metrics(ranking, relevant, cutoffs)
            covered = _span_is_covered(
                [by_id[hit_id] for hit_id in ranking],
                {
                    "source_id": task["source_id"],
                    "element_id": element_id,
                    "char_start": anchor_start,
                    "char_end": anchor_end,
                    "source_text": source_element["text"],
                },
            )
            rows.append(
                {
                    "task_id": task["task_id"],
                    "source_id": task["source_id"],
                    "reference_element_id": element_id,
                    "reference_span": [anchor_start, anchor_end],
                    "shortlist_candidate_count": len(hit_ids),
                    "retrieved_candidate_ids": ranking,
                    "metrics": metrics,
                    "evidence_span_covered": covered,
                    "rerank_latency_ms": latency_ms,
                }
            )
        report_arms[strategy] = {
            "bm25": baseline["strategies"][strategy]["metrics_macro_average"],
            "candidate_vector_rerank": {
                metric: statistics.fmean(row["metrics"][metric] for row in rows)
                for metric in rows[0]["metrics"]
            },
            "bm25_span_coverage": statistics.fmean(
                row["evidence_span_covered"] for row in baseline["strategies"][strategy]["tasks"]
            ),
            "candidate_vector_span_coverage": statistics.fmean(
                row["evidence_span_covered"] for row in rows
            ),
            "mean_rerank_latency_ms": statistics.fmean(row["rerank_latency_ms"] for row in rows),
            "tasks": rows,
        }

    report = {
        "schema": "papertrail.true-candidate-rerank-report.v1",
        "scope": scope,
        "shortlist_limit": SHORTLIST_LIMIT,
        "provider_calls_this_run": calls_new,
        "provider_input_tokens_this_run": tokens_new,
        "estimated_provider_cost_usd_this_run": str(
            price * Decimal(tokens_new) / Decimal(1_000_000)
        ),
        "cache": cache.inspect(batches, price),
        "arms": report_arms,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": "completed", "output": str(output), "scope": scope}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EmbeddingError, OSError, ValueError, KeyError, StopIteration) as error:
        code = error.code if isinstance(error, EmbeddingError) else type(error).__name__
        print(f"True candidate rerank diagnostic failed: {code}", file=sys.stderr)
        raise SystemExit(2) from None
