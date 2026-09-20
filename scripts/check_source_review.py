"""Validate V01 research records without fetching or publishing product data."""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def validate(review: dict) -> list[str]:
    errors = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    def valid_url(value: object) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username

    require(review.get("record_kind") == "feasibility_review_not_catalog", "Not a research record")
    require(review.get("publishable") is False, "Research must not be publishable")
    require(review.get("published_skus") == 0 and review.get("published_offers") == 0,
            "V01 has no published catalog or offers")
    sources = review.get("sources", [])
    source_ids = [item["source_id"] for item in sources]
    require(len(source_ids) == len(set(source_ids)), "Duplicate source IDs")
    require(Counter(item["category"] for item in sources) ==
            Counter({"cpu": 1, "motherboard": 1, "laptop": 1, "offer": 1}),
            "Expected exactly the four reviewed source categories")
    probes = review.get("probes", [])
    ids = [item["id"] for item in probes]
    require(len(ids) == len(set(ids)), "Duplicate probe IDs")
    readable = Counter()
    for probe in probes:
        label = probe["id"]
        require(probe["source_id"] in source_ids, f"{label}: unknown source")
        require(probe.get("publishable") is False, f"{label}: research probe cannot publish")
        require(valid_url(probe.get("url")), f"{label}: missing HTTPS evidence URL")
        date.fromisoformat(probe["checked_on"])
        require(probe.get("http_status") is None, f"{label}: no original HTTP status was observed")
        require(bool(probe.get("missing_fields")), f"{label}: known gaps must remain recorded")
        require(probe.get("outcome") in {"readable", "empty_body", "tool_error", "insufficient_body"},
                f"{label}: unknown outcome")
        if probe.get("outcome") == "readable":
            require(bool(probe.get("field_locations")), f"{label}: readable fields need locators")
            readable[probe["source_id"]] += 1
        else:
            require(bool(probe.get("failure_reason")), f"{label}: failure needs an observation")
            require(probe.get("field_locations") == [], f"{label}: failed detail has no adopted facts")
    for source in sources:
        label = source["source_id"]
        require(source.get("automated_ingestion_enabled") is False, f"{label}: ingestion not authorized")
        require(source.get("publication_enabled") is False, f"{label}: publication not authorized")
        require(source.get("permission_status") in {"permission_required", "automated_collection_restricted",
                                                    "not_verified", "not_configured"},
                f"{label}: unexpected permission status")
        if source.get("acceptance_basis") == "five_readable_samples":
            require(readable[label] >= 5, f"{label}: fewer than five readable samples")
        elif source.get("acceptance_basis") == "documented_channel_failure":
            failure = source.get("channel_failure") or {}
            require(all(failure.get(key) for key in ("code", "locator", "observation")),
                    f"{label}: incomplete channel failure")
            require(valid_url(failure.get("evidence_url")), f"{label}: failure evidence URL missing")
        else:
            errors.append(f"{label}: missing acceptance basis")
    decision = review.get("decision", {})
    require(decision.get("offer_path") == "manual_reviewed_import", "Expected manual offer decision")
    require(decision.get("real_data_release_ready") is False, "Real data is not release-ready")
    require(decision.get("manual_provider_implemented") is False, "Provider has not been implemented")
    return errors


def main() -> int:
    try:
        review = json.loads((ROOT / "data/manifests/v01-source-review.json").read_text(encoding="utf-8"))
        errors = validate(review)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"FAIL: malformed research record: {exc}")
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(review['sources'])} sources, {len(review['probes'])} probes; publication disabled.")
    print("Scope: record consistency only; not proof of authorization, source freshness or application behavior.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
