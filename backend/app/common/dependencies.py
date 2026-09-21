import asyncio

from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.common.config import Settings
from app.common.contracts import DependencyChecks, ReadyResponse

SCHEMA_REVISION = "0004_imports"


class Dependencies:
    def __init__(self, settings: Settings):
        self.engine = (
            create_engine(
                settings.database_url.get_secret_value(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=0,
                pool_timeout=2,
                connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
            )
            if settings.database_url.get_secret_value()
            else None
        )
        self.redis = (
            Redis.from_url(
                settings.redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2
            )
            if settings.redis_url.get_secret_value()
            else None
        )

    def _probe_database(self) -> str:
        if self.engine is None:
            return "not_configured"
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            exists = connection.scalar(text("SELECT to_regclass('alembic_version')"))
            if not exists:
                return "migration_required"
            versions = (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
            return "ready" if versions == [SCHEMA_REVISION] else "migration_required"

    async def database_status(self) -> str:
        try:
            async with asyncio.timeout(3):
                # Keep libpq off the event loop, including Windows' Proactor event loop.
                return await asyncio.to_thread(self._probe_database)
        except (SQLAlchemyError, OSError, TimeoutError):
            return "unavailable"

    async def redis_status(self) -> str:
        if self.redis is None:
            return "disabled"
        try:
            async with asyncio.timeout(3):
                return "ready" if await self.redis.ping() else "unavailable"
        except Exception:
            # Dependency errors are exposed only as a state, never as a URL or exception message.
            return "unavailable"

    async def readiness(self) -> ReadyResponse:
        database, redis = await asyncio.gather(self.database_status(), self.redis_status())
        return ReadyResponse(
            status="ready" if database == "ready" and redis != "unavailable" else "not_ready",
            checks=DependencyChecks(database=database, redis=redis),
        )

    async def close(self) -> None:
        if self.engine:
            await asyncio.to_thread(self.engine.dispose)
        if self.redis:
            await self.redis.aclose()
