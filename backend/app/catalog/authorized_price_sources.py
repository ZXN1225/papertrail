"""Configuration-only registry for authorized price APIs.

This module deliberately has no HTTP client. It prevents an arbitrary provider, URL,
or browser request from being enabled before an approved adapter is implemented.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AuthorizedPriceSourceStatus:
    source_id: Literal["jd_union"]
    display_name: str
    configured: bool
    required_environment: tuple[str, ...]
    permitted_fields: tuple[str, ...]


_JD_UNION_REQUIRED = (
    "JD_UNION_PERMISSION_REFERENCE",
    "JD_UNION_APP_KEY",
    "JD_UNION_APP_SECRET",
    "JD_UNION_SITE_ID",
)


def statuses(settings) -> tuple[AuthorizedPriceSourceStatus, ...]:
    """Return safe, credential-free status metadata for the fixed source registry."""
    return (
        AuthorizedPriceSourceStatus(
            source_id="jd_union",
            display_name="京东联盟",
            configured="jd_union" in settings.authorized_price_source_ids,
            required_environment=_JD_UNION_REQUIRED,
            permitted_fields=(
                "exact_platform_sku",
                "listed_price",
                "promotion_scope",
                "seller_or_self_operated_flag",
                "listing_url",
                "observed_at",
            ),
        ),
    )
