"""PurchasingService — PO lifecycle + goods receipt (T9 / M19).

Partial receiving supported. Stock moves only on GRN finalize via Inventory.
Supplier liability posts through Accounting on GRN finalize.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.accounting.service import AccountingService
from app.core_platform.inventory.service import InventoryService
from app.core_platform.shared import idempotency as idem
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.accounting import FinancialEntryType
from app.models.base import utc_now
from app.models.inventory import StockMovementType
from app.models.parties import Party, PartyBusinessLink, PartyRelationship, LinkStatus
from app.models.purchasing import (
    GoodsReceipt,
    GoodsReceiptLine,
    GoodsReceiptStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchasePayment,
)


class PurchasingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_supplier(self, business_id: UUID, party_id: UUID) -> None:
        party = await self._session.get(Party, party_id)
        if party is None or party.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Supplier party not found")
        link = (
            await self._session.exec(
                select(PartyBusinessLink).where(
                    PartyBusinessLink.business_id == business_id,
                    PartyBusinessLink.party_id == party_id,
                    PartyBusinessLink.relationship == PartyRelationship.SUPPLIER,
                    PartyBusinessLink.status == LinkStatus.ACTIVE,
                    PartyBusinessLink.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if link is None:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "Party is not an active supplier for this business",
            )

    async def _next_po_number(self, business_id: UUID) -> str:
        rows = (
            await self._session.exec(
                select(PurchaseOrder).where(PurchaseOrder.business_id == business_id)
            )
        ).all()
        return f"PO-{len(rows) + 1:05d}"

    async def _next_grn_number(self, business_id: UUID) -> str:
        rows = (
            await self._session.exec(
                select(GoodsReceipt).where(GoodsReceipt.business_id == business_id)
            )
        ).all()
        return f"GRN-{len(rows) + 1:05d}"

    async def _get_po(self, business_id: UUID, po_id: UUID) -> PurchaseOrder:
        po = await self._session.get(PurchaseOrder, po_id)
        if po is None or po.deleted_at is not None or po.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Purchase order not found")
        return po

    async def _po_lines(self, po_id: UUID) -> list[PurchaseOrderLine]:
        return list(
            (
                await self._session.exec(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.purchase_order_id == po_id,
                        PurchaseOrderLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )

    async def create_order(
        self,
        *,
        business_id: UUID,
        party_id: UUID,
        lines: list[dict],
        branch_id: UUID | None = None,
        location_id: UUID | None = None,
        notes: str | None = None,
        actor_user_id: UUID | None = None,
        currency: str = "KES",
    ) -> PurchaseOrder:
        if not lines:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "At least one line required")
        await self._require_supplier(business_id, party_id)
        number = await self._next_po_number(business_id)
        po = PurchaseOrder(
            id=uuid4(),
            business_id=business_id,
            party_id=party_id,
            branch_id=branch_id,
            location_id=location_id,
            status=PurchaseOrderStatus.DRAFT,
            document_number=number,
            currency=currency,
            notes=notes,
            actor_user_id=actor_user_id,
        )
        self._session.add(po)
        await self._session.flush()
        for raw in lines:
            qty = Decimal(str(raw["quantity_ordered"]))
            cost = Decimal(str(raw["unit_cost"]))
            if qty <= 0:
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED, "quantity_ordered must be positive"
                )
            self._session.add(
                PurchaseOrderLine(
                    id=uuid4(),
                    business_id=business_id,
                    purchase_order_id=po.id,
                    product_id=raw["product_id"],
                    description=str(raw.get("description") or "Line"),
                    quantity_ordered=qty,
                    quantity_received=Decimal("0"),
                    unit_cost=cost,
                )
            )
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="purchasing.order.create",
            event_type="purchasing.order.created",
            resource_type="purchase_order",
            resource_id=po.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"number": number},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(po)
        return po

    async def confirm_order(
        self, *, business_id: UUID, po_id: UUID, actor_user_id: UUID | None = None
    ) -> PurchaseOrder:
        po = await self._get_po(business_id, po_id)
        if po.status != PurchaseOrderStatus.DRAFT:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"Cannot confirm PO in status {po.status.value}",
            )
        po.status = PurchaseOrderStatus.CONFIRMED
        po.touch()
        self._session.add(po)
        await self._session.commit()
        await self._session.refresh(po)
        return po

    async def cancel_order(
        self, *, business_id: UUID, po_id: UUID, actor_user_id: UUID | None = None
    ) -> PurchaseOrder:
        po = await self._get_po(business_id, po_id)
        if po.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CONFIRMED):
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "Only draft/confirmed POs with no receipts can be cancelled",
            )
        lines = await self._po_lines(po.id)
        if any(ln.quantity_received > 0 for ln in lines):
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "Cannot cancel PO after goods have been received",
            )
        po.status = PurchaseOrderStatus.CANCELLED
        po.touch()
        self._session.add(po)
        await self._session.commit()
        await self._session.refresh(po)
        return po

    async def create_receipt(
        self,
        *,
        business_id: UUID,
        purchase_order_id: UUID,
        location_id: UUID,
        lines: list[dict],
        notes: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> GoodsReceipt:
        """Create draft GRN. lines: [{purchase_order_line_id, quantity}, ...]."""
        if not lines:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "At least one line required")
        po = await self._get_po(business_id, purchase_order_id)
        if po.status not in (
            PurchaseOrderStatus.CONFIRMED,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        ):
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "PO must be confirmed or partially_received to receive goods",
            )
        po_lines = {ln.id: ln for ln in await self._po_lines(po.id)}
        number = await self._next_grn_number(business_id)
        grn = GoodsReceipt(
            id=uuid4(),
            business_id=business_id,
            purchase_order_id=po.id,
            location_id=location_id,
            status=GoodsReceiptStatus.DRAFT,
            document_number=number,
            notes=notes,
            actor_user_id=actor_user_id,
        )
        self._session.add(grn)
        await self._session.flush()
        for raw in lines:
            pol_id = raw["purchase_order_line_id"]
            qty = Decimal(str(raw["quantity"]))
            if qty <= 0:
                raise DomainError(DomainErrorCode.VALIDATION_FAILED, "quantity must be positive")
            pol = po_lines.get(pol_id)
            if pol is None or pol.business_id != business_id:
                raise DomainError(DomainErrorCode.NOT_FOUND, "PO line not found")
            remaining = pol.quantity_ordered - pol.quantity_received
            if qty > remaining:
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED,
                    f"Cannot receive {qty}; remaining on line is {remaining}",
                )
            self._session.add(
                GoodsReceiptLine(
                    id=uuid4(),
                    business_id=business_id,
                    goods_receipt_id=grn.id,
                    purchase_order_line_id=pol.id,
                    product_id=pol.product_id,
                    quantity=qty,
                )
            )
        await self._session.commit()
        await self._session.refresh(grn)
        return grn

    async def finalize_receipt(
        self,
        *,
        business_id: UUID,
        receipt_id: UUID,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> GoodsReceipt:
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                g = await self._session.get(GoodsReceipt, prior.resource_id)
                if g is not None:
                    return g

        grn = await self._session.get(GoodsReceipt, receipt_id)
        if grn is None or grn.deleted_at is not None or grn.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Goods receipt not found")
        if grn.status == GoodsReceiptStatus.FINALIZED:
            raise DomainError(DomainErrorCode.ALREADY_PROCESSED, "Receipt already finalized")
        if grn.status != GoodsReceiptStatus.DRAFT:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"Cannot finalize receipt in status {grn.status.value}",
            )

        po = await self._get_po(business_id, grn.purchase_order_id)
        gr_lines = list(
            (
                await self._session.exec(
                    select(GoodsReceiptLine).where(
                        GoodsReceiptLine.goods_receipt_id == grn.id,
                        GoodsReceiptLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        if not gr_lines:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Receipt has no lines")

        inv = InventoryService(self._session)
        liability = Decimal("0")
        po_lines = {ln.id: ln for ln in await self._po_lines(po.id)}

        for gl in gr_lines:
            pol = po_lines[gl.purchase_order_line_id]
            remaining = pol.quantity_ordered - pol.quantity_received
            if gl.quantity > remaining:
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED,
                    f"Over-receive on line {pol.id}: {gl.quantity} > {remaining}",
                )
            await inv._require_product(business_id, gl.product_id)
            await inv._require_location(business_id, grn.location_id)
            await inv._apply_delta(
                business_id=business_id,
                product_id=gl.product_id,
                location_id=grn.location_id,
                delta=gl.quantity,
                movement_type=StockMovementType.RECEIVE,
                actor_user_id=actor_user_id,
                request_id=None,
                reason_code="purchase_receive",
                note=f"GRN {grn.document_number}",
                reference_type="goods_receipt",
                reference_id=grn.id,
                transfer_group_id=None,
            )
            pol.quantity_received = pol.quantity_received + gl.quantity
            pol.touch()
            self._session.add(pol)
            liability += gl.quantity * pol.unit_cost

        await AccountingService(self._session).post_entry(
            business_id=business_id,
            entry_type=FinancialEntryType.SUPPLIER_LIABILITY,
            amount=liability,
            source_type="goods_receipt",
            source_id=grn.id,
            currency=po.currency,
            party_id=po.party_id,
            memo=f"GRN {grn.document_number} for {po.document_number}",
            commit=False,
        )

        grn.status = GoodsReceiptStatus.FINALIZED
        grn.finalized_at = utc_now()
        grn.touch()
        self._session.add(grn)

        # Update PO status from line totals
        all_lines = await self._po_lines(po.id)
        if all(ln.quantity_received >= ln.quantity_ordered for ln in all_lines):
            po.status = PurchaseOrderStatus.RECEIVED
        else:
            po.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
        po.touch()
        self._session.add(po)

        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="purchasing.receipt.finalize",
            event_type="purchasing.receipt.finalized",
            resource_type="goods_receipt",
            resource_id=grn.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"number": grn.document_number, "liability": str(liability)},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="purchasing.receipt.finalize",
                response_body={"id": str(grn.id)},
                response_status=200,
                resource_id=grn.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(grn)
        return grn

    async def record_payment(
        self,
        *,
        business_id: UUID,
        purchase_order_id: UUID,
        amount: Decimal,
        method: str = "cash",
        reference: str | None = None,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> PurchasePayment:
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                p = await self._session.get(PurchasePayment, prior.resource_id)
                if p is not None:
                    return p

        po = await self._get_po(business_id, purchase_order_id)
        if po.status not in (
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
            PurchaseOrderStatus.RECEIVED,
        ):
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "Payments allowed after goods have been received",
            )
        amt = Decimal(amount)
        if amt <= 0:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "amount must be positive")

        pay = PurchasePayment(
            id=uuid4(),
            business_id=business_id,
            purchase_order_id=po.id,
            amount=amt,
            method=method,
            reference=reference,
            paid_at=utc_now(),
            actor_user_id=actor_user_id,
        )
        self._session.add(pay)
        await self._session.flush()
        await AccountingService(self._session).post_entry(
            business_id=business_id,
            entry_type=FinancialEntryType.SUPPLIER_PAYMENT,
            amount=amt,
            source_type="purchase_payment",
            source_id=pay.id,
            currency=po.currency,
            party_id=po.party_id,
            memo=f"Payment on {po.document_number}",
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="purchasing.payment.record",
                response_body={"id": str(pay.id)},
                response_status=201,
                resource_id=pay.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(pay)
        return pay
