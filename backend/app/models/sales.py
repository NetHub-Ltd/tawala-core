"""Sales documents — commercial lifecycle (T8 / M18).

Inventory remains owner of stock; Accounting owns financial entries.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class SalesDocumentType(StrEnum):
    QUOTE = "quote"
    ORDER = "order"
    INVOICE = "invoice"
    RETURN_CREDIT = "return_credit"


class SalesDocumentStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"  # order confirmed / quote accepted
    FINALIZED = "finalized"  # invoice posted; stock+finance effects applied
    CANCELLED = "cancelled"
    VOID = "void"


class SalesDocument(BaseMixin, table=True):
    __tablename__ = "sales_documents"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "document_type",
            "document_number",
            name="uq_sales_doc_biz_type_number",
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    branch_id: UUID | None = Field(default=None, foreign_key="branches.id")
    location_id: UUID | None = Field(default=None, foreign_key="locations.id")
    party_id: UUID | None = Field(default=None, foreign_key="parties.id", index=True)
    document_type: SalesDocumentType = str_enum_col(SalesDocumentType.QUOTE)
    status: SalesDocumentStatus = str_enum_col(SalesDocumentStatus.DRAFT)
    document_number: str = Field(max_length=64)
    currency: str = Field(default="KES", max_length=3)
    notes: str | None = Field(default=None, max_length=1024)
    # Lifecycle links
    source_document_id: UUID | None = Field(
        default=None, foreign_key="sales_documents.id"
    )  # quote→order, order→invoice, invoice→return
    finalized_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), nullable=True
    )
    actor_user_id: UUID | None = Field(default=None)


class SalesLine(BaseMixin, table=True):
    __tablename__ = "sales_lines"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    document_id: UUID = Field(foreign_key="sales_documents.id", index=True)
    product_id: UUID | None = Field(default=None, foreign_key="products.id")
    description: str = Field(max_length=255)
    quantity: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))


class SalesPayment(BaseMixin, table=True):
    """Receipt against a finalized invoice (posts accounting entry)."""

    __tablename__ = "sales_payments"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    document_id: UUID = Field(foreign_key="sales_documents.id", index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    method: str = Field(default="cash", max_length=32)
    reference: str | None = Field(default=None, max_length=128)
    received_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    actor_user_id: UUID | None = Field(default=None)
