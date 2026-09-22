"""Liveness and readiness endpoints (SPEC Part F.1)."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.session import check_database, get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok", "service": "tawala-core"}


@router.get("/ready")
async def ready() -> dict[str, str | bool]:
    """Readiness probe — reports database configuration and connectivity."""
    engine = get_engine()
    if engine is None:
        return {
            "status": "ready",
            "service": "tawala-core",
            "database": "not_configured",
            "database_ok": False,
        }
    ok = await check_database()
    return {
        "status": "ready" if ok else "degraded",
        "service": "tawala-core",
        "database": "configured",
        "database_ok": ok,
    }
