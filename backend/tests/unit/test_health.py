"""Health endpoint tests for Core."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    # httpx 0.28 ASGITransport has no lifespan= kwarg; startup is not run.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "tawala-core"


@pytest.mark.asyncio
async def test_ready_reflects_database_config(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "tawala-core"
    assert "database" in body
    assert "database_ok" in body


def test_settings_without_creds_in_development(monkeypatch):
    """Development allows missing creds; database_url property then raises."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    from app.core_platform.shared.settings import Settings, clear_settings_cache

    clear_settings_cache()
    s = Settings()
    assert s.db_host is None
    assert s.app_name == "tawala-core"
    with pytest.raises(RuntimeError, match="DB_HOST"):
        _ = s.database_url
    clear_settings_cache()
