"""InventoryService — sole owner of stock state (T7 / M17).

Negative stock policy (explicit): quantity_on_hand must never go below zero.
Issue/adjust/transfer that would undershoot raises VALIDATION_FAILED.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared import idempotency as idem
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.base import utc_now
from app.models.catalog import Product
from app.models.inventory import StockLevel, StockMovement, StockMovementType
from app.models.organization import Location


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_product(self, business_id: UUID, product_id: UUID) -> Product:
        p = await self._session.get(Product, product_id)
        if p is None or p.deleted_at is not None or p.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Product not found in business")
        return p

    async def _require_location(self, business_id: UUID, location_id: UUID) -> Location:
        loc = await self._session.get(Location, location_id)
        if loc is None or loc.deleted_at is not None or loc.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Location not found in business")
        return loc

    async def _get_or_create_level(
        self, business_id: UUID, product_id: UUID, location_id: UUID
    ) -> StockLevel:
        row = (
            await self._session.exec(
                select(StockLevel).where(
                    StockLevel.business_id == business_id,
                    StockLevel.product_id == product_id,
                    StockLevel.location_id == location_id,
                    StockLevel.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if row is not None:
            return row
        row = StockLevel(
            id=uuid4(),
            business_id=business_id,
            product_id=product_id,
            location_id=location_id,
            quantity_on_hand=Decimal("0"),
            quantity_reserved=Decimal("0"),
            version=1,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    def _validate_qty(self, qty: Decimal) -> Decimal:
        if qty is None:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "quantity is required")
        q = Decimal(qty)
        if q <= 0:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, "quantity must be positive"
            )
        return q

    async def _apply_delta(
        self,
        *,
        business_id: UUID,
        product_id: UUID,
        location_id: UUID,
        delta: Decimal,
        movement_type: StockMovementType,
        actor_user_id: UUID | None,
        request_id: UUID | None,
        reason_code: str | None,
        note: str | None,
        reference_type: str | None,
        reference_id: UUID | None,
        transfer_group_id: UUID | None,
        allow_negative: bool = False,
    ) -> tuple[StockLevel, StockMovement]:
        level = await self._get_or_create_level(business_id, product_id, location_id)
        before = Decimal(level.quantity_on_hand)
        after = before + delta
        if not allow_negative and after < 0:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"Insufficient stock: on_hand={before}, delta={delta}",
            )
        level.quantity_on_hand = after
        level.version = int(level.version or 1) + 1
        level.touch()
        self._session.add(level)

        mov = StockMovement(
            id=uuid4(),
            business_id=business_id,
            product_id=product_id,
            location_id=location_id,
            movement_type=movement_type,
            quantity_delta=delta,
            quantity_before=before,
            quantity_after=after,
            reason_code=reason_code,
            note=note,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reference_type=reference_type,
            reference_id=reference_id,
            transfer_group_id=transfer_group_id,
            occurred_at=utc_now(),
        )
        self._session.add(mov)
        await self._session.flush()
        return level, mov

    async def _record_activity(
        self,
        *,
        action: str,
        event_type: str,
        resource_id: UUID,
        business_id: UUID,
        actor_user_id: UUID | None,
        payload: dict,
    ) -> None:
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action=action,
            event_type=event_type,
            resource_type="stock_movement",
            resource_id=resource_id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload=payload,
            after=payload,
            commit=False,
        )

    async def get_level(
        self, business_id: UUID, product_id: UUID, location_id: UUID
    ) -> StockLevel | None:
        return (
            await self._session.exec(
                select(StockLevel).where(
                    StockLevel.business_id == business_id,
                    StockLevel.product_id == product_id,
                    StockLevel.location_id == location_id,
                    StockLevel.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()

    async def list_levels(
        self, business_id: UUID, *, location_id: UUID | None = None
    ) -> list[StockLevel]:
        stmt = select(StockLevel).where(
            StockLevel.business_id == business_id,
            StockLevel.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        if location_id is not None:
            stmt = stmt.where(StockLevel.location_id == location_id)
        return list((await self._session.exec(stmt)).all())

    async def list_movements(
        self,
        business_id: UUID,
        *,
        product_id: UUID | None = None,
        location_id: UUID | None = None,
        limit: int = 100,
    ) -> list[StockMovement]:
        stmt = select(StockMovement).where(
            StockMovement.business_id == business_id,
            StockMovement.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        if location_id is not None:
            stmt = stmt.where(StockMovement.location_id == location_id)
        stmt = stmt.order_by(StockMovement.occurred_at.desc()).limit(limit)  # type: ignore[attr-defined]
        return list((await self._session.exec(stmt)).all())

    async def receive(
        self,
        *,
        business_id: UUID,
        product_id: UUID,
        location_id: UUID,
        quantity: Decimal,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        note: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> StockMovement:
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                m = await self._session.get(StockMovement, prior.resource_id)
                if m is not None:
                    return m

        await self._require_product(business_id, product_id)
        await self._require_location(business_id, location_id)
        qty = self._validate_qty(quantity)
        _, mov = await self._apply_delta(
            business_id=business_id,
            product_id=product_id,
            location_id=location_id,
            delta=qty,
            movement_type=StockMovementType.RECEIVE,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason_code=None,
            note=note,
            reference_type=reference_type,
            reference_id=reference_id,
            transfer_group_id=None,
        )
        await self._record_activity(
            action="inventory.receive",
            event_type="stock.received",
            resource_id=mov.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={
                "product_id": str(product_id),
                "location_id": str(location_id),
                "quantity": str(qty),
            },
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="inventory.receive",
                response_body={"id": str(mov.id)},
                response_status=201,
                resource_id=mov.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(mov)
        return mov

    async def issue(
        self,
        *,
        business_id: UUID,
        product_id: UUID,
        location_id: UUID,
        quantity: Decimal,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        note: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> StockMovement:
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                m = await self._session.get(StockMovement, prior.resource_id)
                if m is not None:
                    return m

        await self._require_product(business_id, product_id)
        await self._require_location(business_id, location_id)
        qty = self._validate_qty(quantity)
        _, mov = await self._apply_delta(
            business_id=business_id,
            product_id=product_id,
            location_id=location_id,
            delta=-qty,
            movement_type=StockMovementType.ISSUE,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason_code=None,
            note=note,
            reference_type=reference_type,
            reference_id=reference_id,
            transfer_group_id=None,
            allow_negative=False,
        )
        await self._record_activity(
            action="inventory.issue",
            event_type="stock.issued",
            resource_id=mov.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={
                "product_id": str(product_id),
                "location_id": str(location_id),
                "quantity": str(qty),
            },
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="inventory.issue",
                response_body={"id": str(mov.id)},
                response_status=201,
                resource_id=mov.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(mov)
        return mov

    async def adjust(
        self,
        *,
        business_id: UUID,
        product_id: UUID,
        location_id: UUID,
        quantity_on_hand: Decimal,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        reason_code: str | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
    ) -> StockMovement:
        """Set absolute on-hand quantity (count). Auditable adjust movement."""
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                m = await self._session.get(StockMovement, prior.resource_id)
                if m is not None:
                    return m

        await self._require_product(business_id, product_id)
        await self._require_location(business_id, location_id)
        target = Decimal(quantity_on_hand)
        if target < 0:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "quantity_on_hand cannot be negative",
            )
        level = await self._get_or_create_level(business_id, product_id, location_id)
        before = Decimal(level.quantity_on_hand)
        delta = target - before
        _, mov = await self._apply_delta(
            business_id=business_id,
            product_id=product_id,
            location_id=location_id,
            delta=delta,
            movement_type=StockMovementType.ADJUST,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason_code=reason_code or "count",
            note=note,
            reference_type=None,
            reference_id=None,
            transfer_group_id=None,
            allow_negative=False,
        )
        await self._record_activity(
            action="inventory.adjust",
            event_type="stock.adjusted",
            resource_id=mov.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={
                "product_id": str(product_id),
                "location_id": str(location_id),
                "before": str(before),
                "after": str(target),
                "delta": str(delta),
            },
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="inventory.adjust",
                response_body={"id": str(mov.id)},
                response_status=201,
                resource_id=mov.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(mov)
        return mov

    async def transfer(
        self,
        *,
        business_id: UUID,
        product_id: UUID,
        from_location_id: UUID,
        to_location_id: UUID,
        quantity: Decimal,
        actor_user_id: UUID | None = None,
        request_id: UUID | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[StockMovement, StockMovement]:
        """Atomic transfer: transfer_out + transfer_in, same transfer_group_id."""
        if from_location_id == to_location_id:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "from_location and to_location must differ",
            )
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.response_body:
                out_id = prior.response_body.get("out_id")
                in_id = prior.response_body.get("in_id")
                if out_id and in_id:
                    out_m = await self._session.get(StockMovement, UUID(str(out_id)))
                    in_m = await self._session.get(StockMovement, UUID(str(in_id)))
                    if out_m and in_m:
                        return out_m, in_m

        await self._require_product(business_id, product_id)
        await self._require_location(business_id, from_location_id)
        await self._require_location(business_id, to_location_id)
        qty = self._validate_qty(quantity)
        group_id = uuid4()

        _, out_mov = await self._apply_delta(
            business_id=business_id,
            product_id=product_id,
            location_id=from_location_id,
            delta=-qty,
            movement_type=StockMovementType.TRANSFER_OUT,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason_code=None,
            note=note,
            reference_type="transfer",
            reference_id=group_id,
            transfer_group_id=group_id,
            allow_negative=False,
        )
        _, in_mov = await self._apply_delta(
            business_id=business_id,
            product_id=product_id,
            location_id=to_location_id,
            delta=qty,
            movement_type=StockMovementType.TRANSFER_IN,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason_code=None,
            note=note,
            reference_type="transfer",
            reference_id=group_id,
            transfer_group_id=group_id,
        )
        await self._record_activity(
            action="inventory.transfer",
            event_type="stock.transferred",
            resource_id=out_mov.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={
                "product_id": str(product_id),
                "from_location_id": str(from_location_id),
                "to_location_id": str(to_location_id),
                "quantity": str(qty),
                "transfer_group_id": str(group_id),
            },
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="inventory.transfer",
                response_body={"out_id": str(out_mov.id), "in_id": str(in_mov.id)},
                response_status=201,
                resource_id=out_mov.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(out_mov)
        await self._session.refresh(in_mov)
        return out_mov, in_mov
