"""Async database engine and SQLModel session factory + RLS helpers.

Infrastructure boundary: ``create_async_engine`` / ``async_sessionmaker`` come from
``sqlalchemy.ext.asyncio`` (no SQLModel equivalent). All application sessions are
``sqlmodel.ext.asyncio.session.AsyncSession``. Prefer ``session.exec(select(...))``
for ORM queries; raw SQL (GUCs) goes through ``session.connection().execute`` to
avoid SQLModel's ``session.execute`` deprecation warning.

**RLS GUC lifetime:** With ``NullPool``, SQLAlchemy releases the DB connection on
``commit()``, so PostgreSQL session GUCs cannot survive a commit on their own.
We store the active tenant on ``session.info['tenant_guc']`` and re-apply GUCs on
every new transaction via a SQLAlchemy ``after_begin`` listener. ``set_tenant_guc``
updates that info; ``get_session`` clears it on request end.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.settings import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_guc_listener_registered = False


def _apply_guc_on_connection(connection, *, business_id: str | None, bypass: bool) -> None:
    """Sync apply of RLS GUCs on a live connection (used by after_begin)."""
    if bypass:
        connection.execute(text("SELECT set_config('app.rls_bypass', 'on', false)"))
        connection.execute(text("SELECT set_config('app.current_business_id', '', false)"))
        return
    connection.execute(text("SELECT set_config('app.rls_bypass', 'off', false)"))
    connection.execute(
        text("SELECT set_config('app.current_business_id', :bid, false)"),
        {"bid": business_id or ""},
    )


def _register_guc_listener() -> None:
    """Re-apply tenant GUCs whenever a new transaction begins on a Session."""
    global _guc_listener_registered
    if _guc_listener_registered:
        return

    @event.listens_for(SyncSession, "after_begin")
    def _restore_tenant_guc(session: SyncSession, transaction, connection) -> None:  # noqa: ARG001
        if not get_settings().rls_enabled:
            return
        guc = session.info.get("tenant_guc")
        if not guc:
            return
        _apply_guc_on_connection(
            connection,
            business_id=guc.get("business_id"),
            bypass=bool(guc.get("bypass")),
        )

    _guc_listener_registered = True


def get_engine():
    """Return the process-wide async engine, creating it if credentials are set."""
    global _engine, _session_factory
    settings = get_settings()
    if not settings.db_host:
        return None
    if _engine is None:
        _register_guc_listener()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=settings.database_pool_pre_ping,
            echo=False,
            poolclass=NullPool,
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    get_engine()
    return _session_factory


def reset_engine() -> None:
    """Drop cached engine (tests must call after loop changes)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def dispose_engine() -> None:
    """Dispose engine connections then clear cache."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a SQLModel AsyncSession or raise if DB unset."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError(
            "Database is not configured. Set DB_HOST, DB_USER, "
            "DB_PASSWORD, DB_NAME (optional DB_PORT)."
        )
    async with factory() as session:
        try:
            yield session
        finally:
            # Drop tenant intent so a recycled process never re-applies stale GUCs.
            session.info.pop("tenant_guc", None)


async def set_tenant_guc(
    session: AsyncSession, business_id: UUID | None, *, bypass: bool = False
) -> None:
    """Record and apply tenant GUCs for this session.

    Stores intent on ``session.info['tenant_guc']`` so ``after_begin`` can
    re-apply after every ``commit()`` (NullPool releases connections on commit,
    which would otherwise clear PostgreSQL session GUCs).

    Does **not** call ``session.expire_all()``.
    """
    settings = get_settings()
    if not settings.rls_enabled:
        return
    _register_guc_listener()
    session.info["tenant_guc"] = {
        "business_id": str(business_id) if business_id else None,
        "bypass": bypass,
    }
    # Apply on the current connection/transaction immediately.
    conn = await session.connection()
    if bypass:
        await conn.execute(text("SELECT set_config('app.rls_bypass', 'on', false)"))
        await conn.execute(text("SELECT set_config('app.current_business_id', '', false)"))
        return
    await conn.execute(text("SELECT set_config('app.rls_bypass', 'off', false)"))
    if business_id is None:
        await conn.execute(text("SELECT set_config('app.current_business_id', '', false)"))
    else:
        await conn.execute(
            text("SELECT set_config('app.current_business_id', :bid, false)"),
            {"bid": str(business_id)},
        )


async def check_database() -> bool:
    """Return True if a simple connectivity check succeeds."""
    engine = get_engine()
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


metadata = SQLModel.metadata
