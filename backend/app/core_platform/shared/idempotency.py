"""Idempotency helpers for Core commands."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.idempotency import IdempotencyRecord


async def lookup(
    session: AsyncSession, *, scope: str, key: str
) -> IdempotencyRecord | None:
    return (await session.exec(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
            IdempotencyRecord.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
    )).first()


async def store(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    operation: str,
    response_body: dict[str, Any],
    response_status: int = 200,
    resource_id: UUID | None = None,
    commit: bool = False,
) -> IdempotencyRecord:
    existing = await lookup(session, scope=scope, key=key)
    if existing:
        return existing
    row = IdempotencyRecord(
        id=uuid4(),
        scope=scope,
        key=key,
        operation=operation,
        response_status=response_status,
        response_body=response_body,
        resource_id=resource_id,
    )
    session.add(row)
    if commit:
        await session.commit()
        await session.refresh(row)
    else:
        await session.flush()
    return row


def require_key_format(key: str | None) -> str | None:
    if key is None:
        return None
    key = key.strip()
    if not key:
        return None
    if len(key) > 128:
        raise DomainError(DomainErrorCode.VALIDATION_FAILED, "idempotency_key too long")
    return key
