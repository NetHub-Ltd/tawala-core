"""EntitlementService — product capability grants per Business (T5)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.entitlements.seed import SYSTEM_CAPABILITIES
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.base import utc_now
from app.models.entitlements import BusinessEntitlement, Capability, CapabilityKind


class EntitlementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_catalog_seeded(self) -> int:
        """Idempotently seed SYSTEM_CAPABILITIES. Returns count inserted."""
        inserted = 0
        for code, kind, description in SYSTEM_CAPABILITIES:
            existing = (
                await self._session.exec(select(Capability).where(Capability.code == code))
            ).first()
            if existing is not None:
                continue
            self._session.add(
                Capability(id=uuid4(), code=code, kind=kind, description=description)
            )
            inserted += 1
        if inserted:
            await self._session.commit()
        return inserted

    async def _active_grant(
        self, business_id: UUID, code: str
    ) -> BusinessEntitlement | None:
        now = utc_now()
        row = (
            await self._session.exec(
                select(BusinessEntitlement).where(
                    BusinessEntitlement.business_id == business_id,
                    BusinessEntitlement.capability_code == code,
                    BusinessEntitlement.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if row is None:
            return None
        if row.valid_from is not None and row.valid_from > now:
            return None
        if row.valid_until is not None and row.valid_until <= now:
            return None
        return row

    async def has(self, business_id: UUID, code: str) -> bool:
        return await self._active_grant(business_id, code) is not None

    async def limit(self, business_id: UUID, code: str) -> int | None:
        row = await self._active_grant(business_id, code)
        if row is None:
            return None
        return row.limit_value

    async def require(self, business_id: UUID, code: str) -> None:
        """Deny-by-default: missing or expired entitlement → FORBIDDEN."""
        if not await self.has(business_id, code):
            raise DomainError(
                DomainErrorCode.FORBIDDEN,
                f"Business is not entitled to capability '{code}'",
            )

    async def grant(
        self,
        business_id: UUID,
        code: str,
        *,
        limit_value: int | None = None,
        source: str | None = "manual",
        actor_user_id: UUID | None = None,
    ) -> BusinessEntitlement:
        cap = (
            await self._session.exec(select(Capability).where(Capability.code == code))
        ).first()
        if cap is None:
            raise DomainError(
                DomainErrorCode.NOT_FOUND, f"Unknown capability code: {code}"
            )
        if cap.kind == CapabilityKind.LIMIT and limit_value is None:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"limit_value is required for capability kind 'limit' ({code})",
            )

        existing = (
            await self._session.exec(
                select(BusinessEntitlement).where(
                    BusinessEntitlement.business_id == business_id,
                    BusinessEntitlement.capability_code == code,
                    BusinessEntitlement.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if existing:
            existing.limit_value = limit_value
            existing.source = source
            existing.valid_from = existing.valid_from or utc_now()
            existing.valid_until = None
            existing.touch()
            self._session.add(existing)
            await self._session.flush()
            from app.core_platform.shared.activity import record_activity

            await record_activity(
                self._session,
                action="entitlements.grant",
                event_type="entitlement.updated",
                resource_type="business_entitlement",
                resource_id=existing.id,
                business_id=business_id,
                actor_user_id=actor_user_id,
                after={"code": code, "limit_value": limit_value, "source": source},
                commit=False,
            )
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        row = BusinessEntitlement(
            id=uuid4(),
            business_id=business_id,
            capability_code=code,
            limit_value=limit_value,
            source=source,
            valid_from=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="entitlements.grant",
            event_type="entitlement.granted",
            resource_type="business_entitlement",
            resource_id=row.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            after={"code": code, "limit_value": limit_value, "source": source},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def revoke(
        self,
        business_id: UUID,
        code: str,
        *,
        actor_user_id: UUID | None = None,
    ) -> None:
        row = (
            await self._session.exec(
                select(BusinessEntitlement).where(
                    BusinessEntitlement.business_id == business_id,
                    BusinessEntitlement.capability_code == code,
                    BusinessEntitlement.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if row is None:
            raise DomainError(
                DomainErrorCode.NOT_FOUND, f"No entitlement for capability '{code}'"
            )
        row.soft_delete(by_user_id=actor_user_id)
        self._session.add(row)
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="entitlements.revoke",
            event_type="entitlement.revoked",
            resource_type="business_entitlement",
            resource_id=row.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            after={"code": code},
            commit=False,
        )
        await self._session.commit()

    async def list_for_business(
        self, business_id: UUID
    ) -> list[BusinessEntitlement]:
        rows = (
            await self._session.exec(
                select(BusinessEntitlement).where(
                    BusinessEntitlement.business_id == business_id,
                    BusinessEntitlement.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).all()
        return list(rows)
