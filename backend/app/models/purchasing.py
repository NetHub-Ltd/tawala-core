"""Purchasing documents — PO and goods receipt (T9 / M19)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class GoodsReceiptStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    VOID = "void"


class PurchaseOrder(BaseMixin, table=True):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "document_number", name="uq_po_biz_number"
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    party_id: UUID = Field(foreign_key="parties.id", index=True)  # supplier
    branch_id: UUID | None = Field(default=None, foreign_key="branches.id")
    location_id: UUID | None = Field(default=None, foreign_key="locations.id")
    status: PurchaseOrderStatus = str_enum_col(PurchaseOrderStatus.DRAFT)
    document_number: str = Field(max_length=64)
    currency: str = Field(default="KES", max_length=3)
    notes: str | None = Field(default=None, max_length=1024)
    actor_user_id: UUID | None = Field(default=None)


class PurchaseOrderLine(BaseMixin, table=True):
    __tablename__ = "purchase_order_lines"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    purchase_order_id: UUID = Field(foreign_key="purchase_orders.id", index=True)
    product_id: UUID = Field(foreign_key="products.id")
    description: str = Field(max_length=255)
    quantity_ordered: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    quantity_received: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    unit_cost: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))


class GoodsReceipt(BaseMixin, table=True):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "document_number", name="uq_grn_biz_number"
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    purchase_order_id: UUID = Field(foreign_key="purchase_orders.id", index=True)
    location_id: UUID = Field(foreign_key="locations.id")
    status: GoodsReceiptStatus = str_enum_col(GoodsReceiptStatus.DRAFT)
    document_number: str = Field(max_length=64)
    notes: str | None = Field(default=None, max_length=1024)
    finalized_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), nullable=True
    )
    actor_user_id: UUID | None = Field(default=None)


class GoodsReceiptLine(BaseMixin, table=True):
    __tablename__ = "goods_receipt_lines"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    goods_receipt_id: UUID = Field(foreign_key="goods_receipts.id", index=True)
    purchase_order_line_id: UUID = Field(foreign_key="purchase_order_lines.id")
    product_id: UUID = Field(foreign_key="products.id")
    quantity: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))


class PurchasePayment(BaseMixin, table=True):
    __tablename__ = "purchase_payments"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    purchase_order_id: UUID = Field(foreign_key="purchase_orders.id", index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    method: str = Field(default="cash", max_length=32)
    reference: str | None = Field(default=None, max_length=128)
    paid_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    actor_user_id: UUID | None = Field(default=None)
