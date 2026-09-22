"""ConfigService — per-business key/value configuration."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.configuration import BusinessConfig


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, business_id: UUID, key: str) -> BusinessConfig | None:
        return (await self._session.exec(
            select(BusinessConfig).where(
                BusinessConfig.business_id == business_id,
                BusinessConfig.key == key,
                BusinessConfig.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )).first()

    async def set(
        self,
        business_id: UUID,
        key: str,
        value: dict[str, Any],
        *,
        actor_user_id: UUID | None = None,
    ) -> BusinessConfig:
        """Upsert config key. Emits audit + domain event (T4 audit coverage)."""
        from app.core_platform.shared.activity import record_activity

        existing = await self.get(business_id, key)
        if existing:
            before = {"key": key, "value": existing.value}
            existing.value = value
            existing.touch()
            self._session.add(existing)
            await self._session.flush()
            await record_activity(
                self._session,
                action="organization.config.set",
                event_type="config.updated",
                resource_type="business_config",
                resource_id=existing.id,
                business_id=business_id,
                actor_user_id=actor_user_id,
                before=before,
                after={"key": key, "value": value},
                payload={"key": key},
                commit=False,
            )
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        row = BusinessConfig(
            id=uuid4(),
            business_id=business_id,
            key=key,
            value=value,
        )
        self._session.add(row)
        await self._session.flush()
        await record_activity(
            self._session,
            action="organization.config.set",
            event_type="config.created",
            resource_type="business_config",
            resource_id=row.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            after={"key": key, "value": value},
            payload={"key": key},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def require(self, business_id: UUID, key: str) -> BusinessConfig:
        row = await self.get(business_id, key)
        if row is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, f"Config key not found: {key}")
        return row
