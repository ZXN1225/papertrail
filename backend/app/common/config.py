from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("")
    session_signing_secret: SecretStr = SecretStr("")
    public_base_url: str = "http://localhost:3000"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    llm_provider: Literal["disabled"] = "disabled"

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value():
            try:
                url = make_url(value.get_secret_value())
                valid = url.drivername == "postgresql+psycopg" and bool(url.host and url.database)
            except Exception:
                valid = False
            if not valid:
                raise ValueError("DATABASE_URL must use postgresql+psycopg with host/database")
        return value

    @field_validator("redis_url")
    @classmethod
    def redis_scheme(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value():
            parsed = urlsplit(value.get_secret_value())
            if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
                raise ValueError("REDIS_URL must use redis or rediss")
        return value

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        for origin in [self.public_base_url, *self.origins]:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("Public URL and CORS must be explicit HTTP(S) origins")
        if self.app_env == "production":
            if not self.database_url.get_secret_value() or not self.redis_url.get_secret_value():
                raise ValueError("Production requires DATABASE_URL and REDIS_URL")
            if len(self.session_signing_secret.get_secret_value()) < 32:
                raise ValueError("Production requires a session secret of at least 32 characters")
            if not self.origins or any(
                not origin.startswith("https://")
                for origin in [self.public_base_url, *self.origins]
            ):
                raise ValueError("Production requires explicit HTTPS origins")
        return self
