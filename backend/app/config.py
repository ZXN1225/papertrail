"""Server-side settings with safe, provider-disabled defaults."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    data_storage_path: Path = Path("data/papertrail.sqlite3")
    openalex_api_key: SecretStr | None = None
    llm_provider: Literal["disabled", "openai"] = "disabled"
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    llm_max_output_tokens: int = Field(default=800, ge=64, le=4_096)
    agent_max_steps: int = Field(default=4, ge=1, le=8)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=16)
    agent_deadline_seconds: float = Field(default=45.0, gt=0, le=120)
    embedding_provider: Literal["disabled", "openai"] = "disabled"
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    embedding_price_per_million_usd: float | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def require_credentials_for_enabled_providers(self) -> "Settings":
        if self.llm_provider == "openai" and (not self.llm_api_key or not self.llm_model):
            raise ValueError("LLM_API_KEY and LLM_MODEL are required when LLM_PROVIDER=openai")
        if self.embedding_provider == "openai" and (
            not self.embedding_api_key or not self.embedding_model
        ):
            raise ValueError(
                "EMBEDDING_API_KEY and EMBEDDING_MODEL are required when EMBEDDING_PROVIDER=openai"
            )
        if self.embedding_dimensions is not None and self.embedding_dimensions < 1:
            raise ValueError("EMBEDDING_DIMENSIONS must be a positive integer")
        if self.embedding_dimensions is not None and self.embedding_dimensions > 8_192:
            raise ValueError("EMBEDDING_DIMENSIONS must be at most 8192")
        return self

    @property
    def resolved_data_storage_path(self) -> Path:
        path = self.data_storage_path
        if path.is_absolute():
            return path
        project_root = Path(__file__).resolve().parents[2]
        return (project_root / path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings; secrets remain server-side."""
    return Settings()
