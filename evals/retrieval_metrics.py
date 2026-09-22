"""Deterministic retrieval baselines and information-retrieval metrics for TEST-only datasets."""

import math
import re
from collections import Counter


def tokenize(value):
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.casefold())


def overlap(query, documents):
    terms = set(tokenize(query))
    return sorted(
        ((len(terms.intersection(tokenize(doc["text"]))), doc["doc_id"]) for doc in documents),
        key=lambda item: (-item[0], item[1]),
    )


def bm25(query, documents):
    terms, tokenized = tokenize(query), [tokenize(doc["text"]) for doc in documents]
    if not terms or not documents:
        return []
    average = sum(max(1, len(tokens)) for tokens in tokenized) / len(tokenized)
    frequencies = [Counter(tokens) for tokens in tokenized]
    result = []
    for doc, tokens, counts in zip(documents, tokenized, frequencies, strict=True):
        score = 0.0
        for term in terms:
            if not counts[term]:
                continue
            df = sum(term in item for item in tokenized)
            inverse = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            score += (
                inverse
                * counts[term]
                * 2.2
                / (counts[term] + 1.2 * (0.25 + 0.75 * len(tokens) / average))
            )
        result.append((score, doc["doc_id"]))
    return sorted(result, key=lambda item: (-item[0], item[1]))


def reciprocal_rank_fusion(rankings, constant=60):
    """Fuse independent ranked lists by reciprocal rank; ranks are 1-based."""
    scores = Counter()
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            scores[identifier] += 1 / (constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def metrics(ranked_ids, relevance, k):
    if k < 1:
        raise ValueError("k must be >= 1")
    ranked = ranked_ids[:k]
    first = next(
        (index + 1 for index, item in enumerate(ranked) if relevance.get(item, 0) > 0), None
    )
    hit = 1.0 if first else 0.0
    mrr = 1.0 / first if first else 0.0

    def gain(value):
        return 2**value - 1

    dcg = sum(
        gain(relevance.get(item, 0)) / math.log2(index + 2) for index, item in enumerate(ranked)
    )
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(gain(value) / math.log2(index + 2) for index, value in enumerate(ideal))
    return {"hit": hit, "mrr": mrr, "ndcg": dcg / idcg if idcg else 0.0}
