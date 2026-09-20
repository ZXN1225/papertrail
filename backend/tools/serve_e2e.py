"""Isolated E2E server; refuses non-test databases and migrates only the test database."""

import os

import uvicorn
from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command
from app.common.config import Settings
from app.main import create_app

if __name__ == "__main__":
    config = Settings()
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        local = make_url(config.database_url.get_secret_value())
        if config.app_env != "development" or local.host not in {"localhost", "127.0.0.1"}:
            raise SystemExit("Set TEST_DATABASE_URL explicitly")
        test_url = local.set(database="test_computer").render_as_string(hide_password=False)
    if not (make_url(test_url).database or "").startswith("test_"):
        raise SystemExit("E2E requires a test_* database")
    os.environ["DATABASE_URL"] = test_url
    os.environ["APP_ENV"] = "test"
    # This isolated process binds loopback only; the preview server keeps its own configuration.
    os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:3001"
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:3001"
    command.upgrade(Config("alembic.ini"), "head")
    uvicorn.run(create_app(), host="127.0.0.1", port=8001)
