"""EventService — append domain event + outbox in one unit of work."""

from __future__ import annotations

from datetime import datetime

from app.models.base import utc_now
from typing import Any
from uuid import UUID, uuid4

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.events import DomainEvent, OutboxEntry, OutboxStatus


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def emit(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        payload: dict[str, Any],
        business_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        version: int = 1,
        commit: bool = True,
    ) -> DomainEvent:
        event = DomainEvent(
            id=uuid4(),
            event_type=event_type,
            occurred_at=utc_now(),
            business_id=business_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            version=version,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        outbox = OutboxEntry(
            id=uuid4(),
            event_id=event.id,
            status=OutboxStatus.PENDING,
            attempts=0,
        )
        self._session.add(outbox)
        if commit:
            await self._session.commit()
            await self._session.refresh(event)
        return event
