"""Record audit + domain event for Core mutations (P1 #261)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.audit.service import AuditService
from app.core_platform.events.service import EventService
from app.models.audit import AuditOutcome


async def record_activity(
    session: AsyncSession,
    *,
    action: str,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    business_id: UUID | None,
    actor_user_id: UUID | None,
    payload: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    commit: bool = False,
) -> None:
    """Append audit row and outbox-backed event. Caller commits unless commit=True."""
    await AuditService(session).record(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        business_id=business_id,
        actor_user_id=actor_user_id,
        outcome=AuditOutcome.SUCCESS,
        before=before,
        after=after,
        commit=False,
    )
    await EventService(session).emit(
        event_type=event_type,
        aggregate_type=resource_type,
        aggregate_id=resource_id,
        business_id=business_id,
        actor_user_id=actor_user_id,
        payload=payload or {"id": str(resource_id)},
        commit=False,
    )
    if commit:
        await session.commit()
