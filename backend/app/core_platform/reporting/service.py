"""ReportingService — read-only projections over authoritative domain data (T12).

No writes. No invented financial/inventory truth. Every metric names its source.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.accounting import JournalEntry, JournalStatus
from app.models.inventory import StockLevel
from app.models.purchasing import (
    GoodsReceipt,
    GoodsReceiptStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
)
from app.models.sales import (
    SalesDocument,
    SalesDocumentStatus,
    SalesDocumentType,
    SalesLine,
    SalesPayment,
)


def _day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


class ReportingService:
    """Read-oriented queries. Never mutates Sales, Inventory, Accounting, etc."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sales_by_day(
        self,
        *,
        business_id: UUID,
        day: date,
        branch_id: UUID | None = None,
    ) -> dict:
        """
        Metric: daily finalized invoice revenue (line totals).
        Source: SalesDocument (invoice, FINALIZED) + SalesLine
        Scope: business_id, optional branch_id
        Time: finalized_at within UTC day
        """
        start, end = _day_bounds_utc(day)
        doc_filter = [
            SalesDocument.business_id == business_id,
            SalesDocument.document_type == SalesDocumentType.INVOICE,
            SalesDocument.status == SalesDocumentStatus.FINALIZED,
            SalesDocument.deleted_at.is_(None),  # type: ignore[attr-defined]
            SalesDocument.finalized_at >= start,
            SalesDocument.finalized_at <= end,
        ]
        if branch_id is not None:
            doc_filter.append(SalesDocument.branch_id == branch_id)

        docs = list((await self._session.exec(select(SalesDocument).where(*doc_filter))).all())
        doc_ids = [d.id for d in docs]
        if not doc_ids:
            return {
                "metric": "sales_by_day",
                "source": "sales_documents + sales_lines",
                "day": day.isoformat(),
                "business_id": str(business_id),
                "branch_id": str(branch_id) if branch_id else None,
                "invoice_count": 0,
                "line_total": "0",
            }

        lines = list(
            (
                await self._session.exec(
                    select(SalesLine).where(
                        SalesLine.business_id == business_id,
                        SalesLine.document_id.in_(doc_ids),  # type: ignore[attr-defined]
                        SalesLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        total = sum((ln.line_total for ln in lines), Decimal("0"))
        return {
            "metric": "sales_by_day",
            "source": "sales_documents + sales_lines",
            "day": day.isoformat(),
            "business_id": str(business_id),
            "branch_id": str(branch_id) if branch_id else None,
            "invoice_count": len(docs),
            "line_total": str(total),
        }

    async def sales_by_product(
        self,
        *,
        business_id: UUID,
        day: date | None = None,
        branch_id: UUID | None = None,
        limit: int = 50,
    ) -> dict:
        """
        Metric: product quantities and line totals on finalized invoices.
        Source: SalesDocument + SalesLine (product_id)
        """
        doc_filter = [
            SalesDocument.business_id == business_id,
            SalesDocument.document_type == SalesDocumentType.INVOICE,
            SalesDocument.status == SalesDocumentStatus.FINALIZED,
            SalesDocument.deleted_at.is_(None),  # type: ignore[attr-defined]
        ]
        if day is not None:
            start, end = _day_bounds_utc(day)
            doc_filter.extend(
                [
                    SalesDocument.finalized_at >= start,
                    SalesDocument.finalized_at <= end,
                ]
            )
        if branch_id is not None:
            doc_filter.append(SalesDocument.branch_id == branch_id)

        docs = list((await self._session.exec(select(SalesDocument).where(*doc_filter))).all())
        doc_ids = [d.id for d in docs]
        aggregates: dict[str, dict] = {}
        if doc_ids:
            lines = list(
                (
                    await self._session.exec(
                        select(SalesLine).where(
                            SalesLine.business_id == business_id,
                            SalesLine.document_id.in_(doc_ids),  # type: ignore[attr-defined]
                            SalesLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                        )
                    )
                ).all()
            )
            for ln in lines:
                key = str(ln.product_id) if ln.product_id else "none"
                row = aggregates.setdefault(
                    key,
                    {
                        "product_id": key if ln.product_id else None,
                        "quantity": Decimal("0"),
                        "line_total": Decimal("0"),
                    },
                )
                row["quantity"] += ln.quantity
                row["line_total"] += ln.line_total

        items = sorted(
            aggregates.values(), key=lambda r: r["line_total"], reverse=True
        )[:limit]
        return {
            "metric": "sales_by_product",
            "source": "sales_documents + sales_lines",
            "business_id": str(business_id),
            "day": day.isoformat() if day else None,
            "branch_id": str(branch_id) if branch_id else None,
            "items": [
                {
                    "product_id": i["product_id"],
                    "quantity": str(i["quantity"]),
                    "line_total": str(i["line_total"]),
                }
                for i in items
            ],
        }

    async def sales_by_customer(
        self,
        *,
        business_id: UUID,
        day: date | None = None,
        limit: int = 50,
    ) -> dict:
        """
        Metric: finalized invoice totals by party_id (customer).
        Source: SalesDocument + SalesLine
        """
        doc_filter = [
            SalesDocument.business_id == business_id,
            SalesDocument.document_type == SalesDocumentType.INVOICE,
            SalesDocument.status == SalesDocumentStatus.FINALIZED,
            SalesDocument.deleted_at.is_(None),  # type: ignore[attr-defined]
            SalesDocument.party_id != None,  # type: ignore[attr-defined]
        ]
        if day is not None:
            start, end = _day_bounds_utc(day)
            doc_filter.extend(
                [
                    SalesDocument.finalized_at >= start,
                    SalesDocument.finalized_at <= end,
                ]
            )
        docs = list((await self._session.exec(select(SalesDocument).where(*doc_filter))).all())
        by_party: dict[str, dict] = {}
        for doc in docs:
            pid = str(doc.party_id)
            lines = list(
                (
                    await self._session.exec(
                        select(SalesLine).where(
                            SalesLine.document_id == doc.id,
                            SalesLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                        )
                    )
                ).all()
            )
            total = sum((ln.line_total for ln in lines), Decimal("0"))
            row = by_party.setdefault(
                pid, {"party_id": pid, "invoice_count": 0, "line_total": Decimal("0")}
            )
            row["invoice_count"] += 1
            row["line_total"] += total

        items = sorted(by_party.values(), key=lambda r: r["line_total"], reverse=True)[
            :limit
        ]
        return {
            "metric": "sales_by_customer",
            "source": "sales_documents + sales_lines",
            "business_id": str(business_id),
            "day": day.isoformat() if day else None,
            "items": [
                {
                    "party_id": i["party_id"],
                    "invoice_count": i["invoice_count"],
                    "line_total": str(i["line_total"]),
                }
                for i in items
            ],
        }

    async def inventory_on_hand(
        self, *, business_id: UUID, location_id: UUID | None = None
    ) -> dict:
        """
        Metric: current stock quantities.
        Source: StockLevel (Inventory is authority)
        """
        filters = [
            StockLevel.business_id == business_id,
            StockLevel.deleted_at.is_(None),  # type: ignore[attr-defined]
        ]
        if location_id is not None:
            filters.append(StockLevel.location_id == location_id)
        rows = list((await self._session.exec(select(StockLevel).where(*filters))).all())
        return {
            "metric": "inventory_on_hand",
            "source": "stock_levels",
            "business_id": str(business_id),
            "location_id": str(location_id) if location_id else None,
            "items": [
                {
                    "product_id": str(r.product_id),
                    "location_id": str(r.location_id),
                    "quantity_on_hand": str(r.quantity_on_hand),
                }
                for r in rows
            ],
        }

    async def purchasing_open_pos(self, *, business_id: UUID) -> dict:
        """
        Metric: open purchase orders (not cancelled/fully received).
        Source: PurchaseOrder
        """
        statuses = [
            PurchaseOrderStatus.DRAFT,
            PurchaseOrderStatus.CONFIRMED,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        ]
        rows = list(
            (
                await self._session.exec(
                    select(PurchaseOrder).where(
                        PurchaseOrder.business_id == business_id,
                        PurchaseOrder.status.in_(statuses),  # type: ignore[attr-defined]
                        PurchaseOrder.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        return {
            "metric": "purchasing_open_pos",
            "source": "purchase_orders",
            "business_id": str(business_id),
            "count": len(rows),
            "items": [
                {
                    "id": str(r.id),
                    "document_number": r.document_number,
                    "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                    "party_id": str(r.party_id),
                }
                for r in rows
            ],
        }

    async def grn_finalized_count(
        self, *, business_id: UUID, day: date | None = None
    ) -> dict:
        """
        Metric: finalized goods receipts.
        Source: GoodsReceipt
        """
        filters = [
            GoodsReceipt.business_id == business_id,
            GoodsReceipt.status == GoodsReceiptStatus.FINALIZED,
            GoodsReceipt.deleted_at.is_(None),  # type: ignore[attr-defined]
        ]
        if day is not None:
            start, end = _day_bounds_utc(day)
            # use updated_at/created_at if no finalized_at — check model
            filters.append(GoodsReceipt.created_at >= start)  # type: ignore[arg-type]
            filters.append(GoodsReceipt.created_at <= end)  # type: ignore[arg-type]
        rows = list((await self._session.exec(select(GoodsReceipt).where(*filters))).all())
        return {
            "metric": "grn_finalized_count",
            "source": "goods_receipts",
            "business_id": str(business_id),
            "day": day.isoformat() if day else None,
            "count": len(rows),
        }

    async def payments_collected(
        self, *, business_id: UUID, day: date | None = None
    ) -> dict:
        """
        Metric: customer payment amounts recorded on sales.
        Source: SalesPayment (not Accounting journals)
        """
        filters = [
            SalesPayment.business_id == business_id,
            SalesPayment.deleted_at.is_(None),  # type: ignore[attr-defined]
        ]
        if day is not None:
            start, end = _day_bounds_utc(day)
            filters.append(SalesPayment.received_at >= start)
            filters.append(SalesPayment.received_at <= end)
        rows = list((await self._session.exec(select(SalesPayment).where(*filters))).all())
        total = sum((r.amount for r in rows), Decimal("0"))
        return {
            "metric": "payments_collected",
            "source": "sales_payments",
            "business_id": str(business_id),
            "day": day.isoformat() if day else None,
            "payment_count": len(rows),
            "amount_total": str(total),
        }

    async def journal_posted_count(self, *, business_id: UUID) -> dict:
        """
        Metric: posted journal entries count.
        Source: JournalEntry (Accounting authority)
        """
        rows = list(
            (
                await self._session.exec(
                    select(JournalEntry).where(
                        JournalEntry.business_id == business_id,
                        JournalEntry.status == JournalStatus.POSTED,
                        JournalEntry.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        return {
            "metric": "journal_posted_count",
            "source": "journal_entries",
            "business_id": str(business_id),
            "count": len(rows),
        }
