"""Tawala Core FastAPI application factory.

This is the Core platform entrypoint on branch core/v2.
It must not import product POS modules and must never be merged into main/dev.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core_platform.shared.logging import get_logger, setup_logging
from app.core_platform.shared.settings import get_settings
from app.db.session import check_database, dispose_engine, reset_engine

logger = get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Boot: configure logging, require DB creds, verify connectivity or abort."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        "starting {} env={} log_level={}",
        settings.app_name,
        settings.environment,
        settings.log_level,
    )
    try:
        settings.require_db_credentials()
    except RuntimeError as exc:
        logger.error("startup aborted: {}", exc)
        raise

    reset_engine()
    logger.debug(
        "checking database connectivity host={} port={} db={}",
        settings.db_host,
        settings.db_port,
        settings.db_name,
    )
    ok = await check_database()
    if not ok:
        logger.error(
            "database connectivity check failed — refusing to start "
            "(host={} port={} db={})",
            settings.db_host,
            settings.db_port,
            settings.db_name,
        )
        raise RuntimeError(
            "Database connectivity check failed. "
            "Ensure Postgres is up and DB_HOST/DB_USER/DB_PASSWORD/DB_NAME are correct. "
            "Application will not start."
        )
    logger.info("database connectivity ok")
    yield
    logger.info("shutting down — disposing engine")
    await dispose_engine()
    reset_engine()


def create_application() -> FastAPI:
    """Build the Core API application."""
    application = FastAPI(
        title="Tawala Core",
        version="0.1.0",
        description=(
            "Tawala Core platform foundation. "
            "Isolated branch core/v2 — not the product POS API."
        ),
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


app = create_application()
