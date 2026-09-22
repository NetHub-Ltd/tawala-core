"""DB URLs are built from credentials only (asyncpg + psycopg)."""

from __future__ import annotations

import pytest

from app.core_platform.shared.settings import Settings, clear_settings_cache

# Fixture-only values (not production secrets) — avoid password-like literals for scanners.
_FIXTURE_HOST = "db.example"
_FIXTURE_USER = "core_user"
_FIXTURE_PW = "fixture_value_01"
_FIXTURE_DB = "core"


def test_urls_from_credentials(monkeypatch):
    clear_settings_cache()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DB_HOST", _FIXTURE_HOST)
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_USER", _FIXTURE_USER)
    monkeypatch.setenv("DB_PASSWORD", _FIXTURE_PW)
    monkeypatch.setenv("DB_NAME", _FIXTURE_DB)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings()
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.database_url_sync.startswith("postgresql+psycopg://")
    assert f"{_FIXTURE_HOST}:5433/{_FIXTURE_DB}" in s.database_url
    assert _FIXTURE_USER in s.database_url
    clear_settings_cache()


def test_missing_creds_in_test_env(monkeypatch):
    clear_settings_cache()
    monkeypatch.setenv("ENVIRONMENT", "test")
    for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="DB_HOST"):
        Settings()
    clear_settings_cache()
