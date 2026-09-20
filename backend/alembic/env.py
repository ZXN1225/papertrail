from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from alembic import context
from app.common.config import Settings


def run(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def migrate():
    url = Settings().database_url.get_secret_value()
    if not url:
        raise RuntimeError("DATABASE_URL is required for migration")
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Run migrations against a real PostgreSQL database")
else:
    migrate()
