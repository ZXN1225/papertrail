"""Run integration checks against the explicitly created local test database."""

import os

import pytest
from sqlalchemy.engine import make_url

from app.common.config import Settings

if __name__ == "__main__":
    config = Settings()
    url = make_url(config.database_url.get_secret_value())
    if config.app_env != "development" or url.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This helper is only for a local development database")
    os.environ["TEST_DATABASE_URL"] = url.set(database="test_computer").render_as_string(
        hide_password=False
    )
    if config.redis_url.get_secret_value():
        os.environ["TEST_REDIS_URL"] = config.redis_url.get_secret_value()
    raise SystemExit(pytest.main(["-q"]))
