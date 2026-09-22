import pytest
from pydantic import ValidationError

from app.catalog.authorized_price_sources import statuses
from app.common.config import Settings


def settings(**overrides):
    return Settings(_env_file=None, app_env="test", database_url="", redis_url="", **overrides)


def test_authorized_price_sources_are_disabled_by_default():
    source = statuses(settings())[0]
    assert source.source_id == "jd_union"
    assert source.configured is False
    assert "JD_UNION_APP_SECRET" in source.required_environment


@pytest.mark.parametrize("source_ids", ["unknown_source", "jd_union,jd_union"])
def test_only_fixed_unique_sources_can_be_selected(source_ids):
    with pytest.raises(ValidationError):
        settings(authorized_price_sources=source_ids)


@pytest.mark.parametrize(
    "missing",
    [
        "jd_union_permission_reference",
        "jd_union_app_key",
        "jd_union_app_secret",
        "jd_union_site_id",
    ],
)
def test_selected_jd_union_requires_permission_and_all_credentials(missing):
    values = {
        "authorized_price_sources": "jd_union",
        "jd_union_permission_reference": "contract/JD-UNION-2026",
        "jd_union_app_key": "test-app-key",
        "jd_union_app_secret": "test-app-secret",
        "jd_union_site_id": "test-site-id",
    }
    values[missing] = ""
    with pytest.raises(ValidationError):
        settings(**values)


def test_complete_jd_union_configuration_is_visible_without_exposing_secrets():
    configured = settings(
        authorized_price_sources="jd_union",
        jd_union_permission_reference="contract/JD-UNION-2026",
        jd_union_app_key="test-app-key",
        jd_union_app_secret="test-app-secret",
        jd_union_site_id="test-site-id",
    )
    source = statuses(configured)[0]
    assert source.configured is True
    assert "test-app-secret" not in repr(source)
