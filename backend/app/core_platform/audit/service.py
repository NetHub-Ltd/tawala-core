"""AuditService — append-only audit trail."""

from __future__ import annotations

from datetime import datetime

from app.models.base import utc_now
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.audit import AuditOutcome, AuditRecord


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        business_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        request_id: UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        commit: bool = True,
    ) -> AuditRecord:
        row = AuditRecord(
            id=uuid4(),
            business_id=business_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            request_id=request_id,
            before=before,
            after=after,
            reason=reason,
            occurred_at=utc_now(),
        )
        self._session.add(row)
        if commit:
            await self._session.commit()
            await self._session.refresh(row)
        return row

    async def list_for_business(
        self, business_id: UUID, *, limit: int = 100
    ) -> list[AuditRecord]:
        result = await self._session.exec(
            select(AuditRecord)
            .where(AuditRecord.business_id == business_id)
            .order_by(AuditRecord.occurred_at.desc())
            .limit(limit)
        )
        return list(result.all())
