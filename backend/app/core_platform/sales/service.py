"""SalesService — commercial document lifecycle (T8 / M18)."""

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
from app.models.inventory import StockMovementType
from app.models.base import utc_now
from app.models.sales import (
    SalesDocument,
    SalesDocumentStatus,
    SalesDocumentType,
    SalesLine,
    SalesPayment,
)

# Allowed transitions: (type, from_status) -> set of to_status
_TRANSITIONS: dict[tuple[SalesDocumentType, SalesDocumentStatus], set[SalesDocumentStatus]] = {
    (SalesDocumentType.QUOTE, SalesDocumentStatus.DRAFT): {
        SalesDocumentStatus.CONFIRMED,
        SalesDocumentStatus.CANCELLED,
    },
    (SalesDocumentType.QUOTE, SalesDocumentStatus.CONFIRMED): {
        SalesDocumentStatus.CANCELLED,
    },
    (SalesDocumentType.ORDER, SalesDocumentStatus.DRAFT): {
        SalesDocumentStatus.CONFIRMED,
        SalesDocumentStatus.CANCELLED,
    },
    (SalesDocumentType.ORDER, SalesDocumentStatus.CONFIRMED): {
        SalesDocumentStatus.CANCELLED,
    },
    (SalesDocumentType.INVOICE, SalesDocumentStatus.DRAFT): {
        SalesDocumentStatus.FINALIZED,
        SalesDocumentStatus.CANCELLED,
    },
    (SalesDocumentType.INVOICE, SalesDocumentStatus.FINALIZED): {
        SalesDocumentStatus.VOID,
    },
    (SalesDocumentType.RETURN_CREDIT, SalesDocumentStatus.DRAFT): {
        SalesDocumentStatus.FINALIZED,
        SalesDocumentStatus.CANCELLED,
    },
}

_TYPE_PREFIX = {
    SalesDocumentType.QUOTE: "QUO",
    SalesDocumentType.ORDER: "ORD",
    SalesDocumentType.INVOICE: "INV",
    SalesDocumentType.RETURN_CREDIT: "RCN",
}


class SalesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _next_number(self, business_id: UUID, doc_type: SalesDocumentType) -> str:
        prefix = _TYPE_PREFIX[doc_type]
        rows = (
            await self._session.exec(
                select(SalesDocument).where(
                    SalesDocument.business_id == business_id,
                    SalesDocument.document_type == doc_type,
                )
            )
        ).all()
        seq = len(rows) + 1
        return f"{prefix}-{seq:05d}"

    async def _lines(self, document_id: UUID) -> list[SalesLine]:
        return list(
            (
                await self._session.exec(
                    select(SalesLine).where(
                        SalesLine.document_id == document_id,
                        SalesLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )

    async def _get_doc(self, business_id: UUID, document_id: UUID) -> SalesDocument:
        doc = await self._session.get(SalesDocument, document_id)
        if doc is None or doc.deleted_at is not None or doc.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Sales document not found")
        return doc

    def _assert_transition(
        self, doc: SalesDocument, new_status: SalesDocumentStatus
    ) -> None:
        allowed = _TRANSITIONS.get((doc.document_type, doc.status), set())
        if new_status not in allowed:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"Invalid transition {doc.document_type.value}:{doc.status.value} → {new_status.value}",
            )

    async def create_document(
        self,
        *,
        business_id: UUID,
        document_type: SalesDocumentType,
        party_id: UUID | None = None,
        branch_id: UUID | None = None,
        location_id: UUID | None = None,
        notes: str | None = None,
        source_document_id: UUID | None = None,
        lines: list[dict],
        actor_user_id: UUID | None = None,
        currency: str = "KES",
    ) -> SalesDocument:
        if not lines:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "At least one line required")
        if document_type == SalesDocumentType.RETURN_CREDIT and not source_document_id:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "return_credit requires source_document_id (original invoice)",
            )
        if source_document_id:
            src = await self._get_doc(business_id, source_document_id)
            if document_type == SalesDocumentType.RETURN_CREDIT:
                if src.document_type != SalesDocumentType.INVOICE or src.status != SalesDocumentStatus.FINALIZED:
                    raise DomainError(
                        DomainErrorCode.VALIDATION_FAILED,
                        "Return must reference a finalized invoice",
                    )

        number = await self._next_number(business_id, document_type)
        doc = SalesDocument(
            id=uuid4(),
            business_id=business_id,
            branch_id=branch_id,
            location_id=location_id,
            party_id=party_id,
            document_type=document_type,
            status=SalesDocumentStatus.DRAFT,
            document_number=number,
            currency=currency,
            notes=notes,
            source_document_id=source_document_id,
            actor_user_id=actor_user_id,
        )
        self._session.add(doc)
        await self._session.flush()
        for raw in lines:
            qty = Decimal(str(raw["quantity"]))
            price = Decimal(str(raw["unit_price"]))
            if qty <= 0:
                raise DomainError(DomainErrorCode.VALIDATION_FAILED, "line quantity must be positive")
            line = SalesLine(
                id=uuid4(),
                business_id=business_id,
                document_id=doc.id,
                product_id=raw.get("product_id"),
                description=str(raw.get("description") or "Line"),
                quantity=qty,
                unit_price=price,
                line_total=qty * price,
            )
            self._session.add(line)
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="sales.document.create",
            event_type="sales.document.created",
            resource_type="sales_document",
            resource_id=doc.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"type": document_type.value, "number": number},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def convert_quote_to_order(
        self, *, business_id: UUID, quote_id: UUID, actor_user_id: UUID | None = None
    ) -> SalesDocument:
        quote = await self._get_doc(business_id, quote_id)
        if quote.document_type != SalesDocumentType.QUOTE:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Not a quote")
        self._assert_transition(quote, SalesDocumentStatus.CONFIRMED)
        quote.status = SalesDocumentStatus.CONFIRMED
        quote.touch()
        self._session.add(quote)
        lines = await self._lines(quote.id)
        order = await self.create_document(
            business_id=business_id,
            document_type=SalesDocumentType.ORDER,
            party_id=quote.party_id,
            branch_id=quote.branch_id,
            location_id=quote.location_id,
            notes=quote.notes,
            source_document_id=quote.id,
            lines=[
                {
                    "product_id": ln.product_id,
                    "description": ln.description,
                    "quantity": ln.quantity,
                    "unit_price": ln.unit_price,
                }
                for ln in lines
            ],
            actor_user_id=actor_user_id,
            currency=quote.currency,
        )
        return order

    async def convert_order_to_invoice(
        self, *, business_id: UUID, order_id: UUID, actor_user_id: UUID | None = None
    ) -> SalesDocument:
        order = await self._get_doc(business_id, order_id)
        if order.document_type != SalesDocumentType.ORDER:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Not an order")
        if order.status not in (SalesDocumentStatus.DRAFT, SalesDocumentStatus.CONFIRMED):
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Order not convertible")
        if order.status == SalesDocumentStatus.DRAFT:
            self._assert_transition(order, SalesDocumentStatus.CONFIRMED)
            order.status = SalesDocumentStatus.CONFIRMED
            order.touch()
            self._session.add(order)
        lines = await self._lines(order.id)
        return await self.create_document(
            business_id=business_id,
            document_type=SalesDocumentType.INVOICE,
            party_id=order.party_id,
            branch_id=order.branch_id,
            location_id=order.location_id,
            notes=order.notes,
            source_document_id=order.id,
            lines=[
                {
                    "product_id": ln.product_id,
                    "description": ln.description,
                    "quantity": ln.quantity,
                    "unit_price": ln.unit_price,
                }
                for ln in lines
            ],
            actor_user_id=actor_user_id,
            currency=order.currency,
        )

    async def finalize_invoice(
        self,
        *,
        business_id: UUID,
        invoice_id: UUID,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> SalesDocument:
        """Finalize invoice once: issue stock via Inventory, post revenue via Accounting."""
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                doc = await self._session.get(SalesDocument, prior.resource_id)
                if doc is not None:
                    return doc

        doc = await self._get_doc(business_id, invoice_id)
        if doc.document_type != SalesDocumentType.INVOICE:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Not an invoice")
        if doc.status == SalesDocumentStatus.FINALIZED:
            raise DomainError(
                DomainErrorCode.ALREADY_PROCESSED, "Invoice already finalized"
            )
        self._assert_transition(doc, SalesDocumentStatus.FINALIZED)
        if not doc.location_id:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                "Invoice location_id required to issue stock",
            )

        lines = await self._lines(doc.id)
        inv = InventoryService(self._session)
        total = Decimal("0")
        for ln in lines:
            total += ln.line_total
            if ln.product_id is not None:
                # Inventory owns stock — issue without nested commit
                await inv._require_product(business_id, ln.product_id)
                await inv._require_location(business_id, doc.location_id)
                await inv._apply_delta(
                    business_id=business_id,
                    product_id=ln.product_id,
                    location_id=doc.location_id,
                    delta=-ln.quantity,
                    movement_type=StockMovementType.ISSUE,
                    actor_user_id=actor_user_id,
                    request_id=None,
                    reason_code="sale",
                    note=f"Invoice {doc.document_number}",
                    reference_type="sales_document",
                    reference_id=doc.id,
                    transfer_group_id=None,
                    allow_negative=False,
                )

        await AccountingService(self._session).post_entry(
            business_id=business_id,
            entry_type=FinancialEntryType.SALE_REVENUE,
            amount=total,
            source_type="sales_document",
            source_id=doc.id,
            currency=doc.currency,
            party_id=doc.party_id,
            memo=f"Finalize {doc.document_number}",
            commit=False,
        )

        doc.status = SalesDocumentStatus.FINALIZED
        doc.finalized_at = utc_now()
        doc.touch()
        self._session.add(doc)

        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="sales.invoice.finalize",
            event_type="sales.invoice.finalized",
            resource_type="sales_document",
            resource_id=doc.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"number": doc.document_number, "total": str(total)},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="sales.invoice.finalize",
                response_body={"id": str(doc.id)},
                response_status=200,
                resource_id=doc.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def record_payment(
        self,
        *,
        business_id: UUID,
        invoice_id: UUID,
        amount: Decimal,
        method: str = "cash",
        reference: str | None = None,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> SalesPayment:
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                pay = await self._session.get(SalesPayment, prior.resource_id)
                if pay is not None:
                    return pay

        doc = await self._get_doc(business_id, invoice_id)
        if doc.document_type != SalesDocumentType.INVOICE:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Payments apply to invoices")
        if doc.status != SalesDocumentStatus.FINALIZED:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, "Invoice must be finalized before payment"
            )
        amt = Decimal(amount)
        if amt <= 0:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "amount must be positive")

        pay = SalesPayment(
            id=uuid4(),
            business_id=business_id,
            document_id=doc.id,
            amount=amt,
            method=method,
            reference=reference,
            received_at=utc_now(),
            actor_user_id=actor_user_id,
        )
        self._session.add(pay)
        await self._session.flush()

        await AccountingService(self._session).post_entry(
            business_id=business_id,
            entry_type=FinancialEntryType.CUSTOMER_RECEIPT,
            amount=amt,
            source_type="sales_payment",
            source_id=pay.id,
            currency=doc.currency,
            party_id=doc.party_id,
            memo=f"Payment on {doc.document_number}",
            commit=False,
        )
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="sales.payment.record",
            event_type="sales.payment.recorded",
            resource_type="sales_payment",
            resource_id=pay.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"invoice_id": str(doc.id), "amount": str(amt)},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="sales.payment.record",
                response_body={"id": str(pay.id)},
                response_status=201,
                resource_id=pay.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(pay)
        return pay

    async def finalize_return(
        self,
        *,
        business_id: UUID,
        return_id: UUID,
        actor_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> SalesDocument:
        """Finalize return/credit: stock back via Inventory receive, accounting return entry."""
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                doc = await self._session.get(SalesDocument, prior.resource_id)
                if doc is not None:
                    return doc

        doc = await self._get_doc(business_id, return_id)
        if doc.document_type != SalesDocumentType.RETURN_CREDIT:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Not a return_credit")
        if doc.status == SalesDocumentStatus.FINALIZED:
            raise DomainError(DomainErrorCode.ALREADY_PROCESSED, "Return already finalized")
        self._assert_transition(doc, SalesDocumentStatus.FINALIZED)
        if not doc.location_id:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, "location_id required for return stock-in"
            )

        lines = await self._lines(doc.id)
        inv = InventoryService(self._session)
        total = Decimal("0")
        for ln in lines:
            total += ln.line_total
            if ln.product_id is not None:
                await inv._require_product(business_id, ln.product_id)
                await inv._require_location(business_id, doc.location_id)
                await inv._apply_delta(
                    business_id=business_id,
                    product_id=ln.product_id,
                    location_id=doc.location_id,
                    delta=ln.quantity,
                    movement_type=StockMovementType.RECEIVE,
                    actor_user_id=actor_user_id,
                    request_id=None,
                    reason_code="sale_return",
                    note=f"Return {doc.document_number}",
                    reference_type="sales_document",
                    reference_id=doc.id,
                    transfer_group_id=None,
                )

        await AccountingService(self._session).post_entry(
            business_id=business_id,
            entry_type=FinancialEntryType.SALE_RETURN,
            amount=total,
            source_type="sales_document",
            source_id=doc.id,
            currency=doc.currency,
            party_id=doc.party_id,
            memo=f"Return {doc.document_number}",
            commit=False,
        )
        doc.status = SalesDocumentStatus.FINALIZED
        doc.finalized_at = utc_now()
        doc.touch()
        self._session.add(doc)
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="sales.return.finalize",
            event_type="sales.return.finalized",
            resource_type="sales_document",
            resource_id=doc.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"number": doc.document_number},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="sales.return.finalize",
                response_body={"id": str(doc.id)},
                response_status=200,
                resource_id=doc.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def cancel(
        self, *, business_id: UUID, document_id: UUID, actor_user_id: UUID | None = None
    ) -> SalesDocument:
        doc = await self._get_doc(business_id, document_id)
        self._assert_transition(doc, SalesDocumentStatus.CANCELLED)
        doc.status = SalesDocumentStatus.CANCELLED
        doc.touch()
        self._session.add(doc)
        await self._session.commit()
        await self._session.refresh(doc)
        return doc
