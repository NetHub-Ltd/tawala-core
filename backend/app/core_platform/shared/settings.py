"""Application settings for Tawala Core.

Database configuration is **credentials only** (no full DATABASE_URL input):

  DB_HOST, DB_PORT (optional, default 5432), DB_USER, DB_PASSWORD, DB_NAME

From those we always build:
  - database_url      → postgresql+asyncpg://…  (SQLModel AsyncSession)
  - database_url_sync → postgresql+psycopg://…  (Alembic)

See docs/architecture/CORE_CONTRACTS.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed Core settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "tawala-core"
    environment: Literal["development", "test", "production"] = Field(
        default="development",
    )
    log_level: str = Field(
        default="DEBUG",
        description="Loguru level (DEBUG|INFO|WARNING|ERROR). Default DEBUG.",
    )

    db_host: str | None = Field(default=None, description="Postgres host")
    db_port: int = Field(default=5432, description="Postgres port")
    db_user: str | None = Field(default=None, description="Postgres user")
    db_password: str | None = Field(default=None, description="Postgres password")
    db_name: str | None = Field(default=None, description="Postgres database name")

    database_pool_pre_ping: bool = True
    rls_enabled: bool = True

    @model_validator(mode="after")
    def _require_db_creds_in_strict_envs(self) -> Settings:
        if self.environment in ("test", "production"):
            self.require_db_credentials()
        return self

    def require_db_credentials(self) -> None:
        missing: list[str] = []
        if not self.db_host:
            missing.append("DB_HOST")
        if not self.db_user:
            missing.append("DB_USER")
        if self.db_password is None:
            missing.append("DB_PASSWORD")
        if not self.db_name:
            missing.append("DB_NAME")
        if missing:
            raise RuntimeError(
                "Database credentials required: "
                + ", ".join(missing)
                + f" (environment={self.environment}). "
                "Set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (optional DB_PORT)."
            )

    def _dsn(self, driver: str) -> str:
        self.require_db_credentials()
        user = quote_plus(self.db_user or "")
        password = quote_plus(self.db_password or "")
        return (
            f"postgresql+{driver}://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL (asyncpg). Built from credentials only."""
        return self._dsn("asyncpg")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Sync SQLAlchemy URL (psycopg) for Alembic. Built from credentials only."""
        return self._dsn("psycopg")

    def require_database_url(self) -> str:
        return self.database_url

    def require_database_url_sync(self) -> str:
        return self.database_url_sync


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
