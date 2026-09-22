"""Accounting Core — chart of accounts, journals, AR/AP bridge (T10 / M20).

Authoritative financial truth. Sales/Purchasing call AccountingService only;
they do not own journal state.
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


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class JournalStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


class FinancialEntryType(StrEnum):
    """Domain event classification still used by Sales/Purchasing adapters."""

    SALE_REVENUE = "sale_revenue"
    CUSTOMER_RECEIPT = "customer_receipt"
    SALE_RETURN = "sale_return"
    SUPPLIER_LIABILITY = "supplier_liability"
    SUPPLIER_PAYMENT = "supplier_payment"


class Account(BaseMixin, table=True):
    """Chart of accounts entry (business-scoped)."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("business_id", "code", name="uq_account_biz_code"),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    code: str = Field(max_length=32, index=True)
    name: str = Field(max_length=128)
    account_type: AccountType = str_enum_col(AccountType.ASSET)
    is_system: bool = Field(default=False)
    currency: str = Field(default="KES", max_length=3)


class JournalEntry(BaseMixin, table=True):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "entry_number", name="uq_journal_biz_number"
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    entry_number: str = Field(max_length=64)
    status: JournalStatus = str_enum_col(JournalStatus.DRAFT)
    source_type: str = Field(max_length=64)
    source_id: UUID = Field(index=True)
    domain_entry_type: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="KES", max_length=3)
    memo: str | None = Field(default=None, max_length=512)
    party_id: UUID | None = Field(default=None)
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    posted_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), nullable=True
    )
    # Reversal: this entry reverses `reverses_entry_id`
    reverses_entry_id: UUID | None = Field(
        default=None, foreign_key="journal_entries.id"
    )
    reversed_by_entry_id: UUID | None = Field(default=None)


class JournalLine(BaseMixin, table=True):
    __tablename__ = "journal_lines"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    journal_entry_id: UUID = Field(foreign_key="journal_entries.id", index=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    debit: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(18, 4), nullable=False)
    )
    credit: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(18, 4), nullable=False)
    )
    party_id: UUID | None = Field(default=None)
    tax_code: str | None = Field(default=None, max_length=32)
    tax_amount: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(18, 4), nullable=False)
    )
    memo: str | None = Field(default=None, max_length=255)


class PaymentAllocation(BaseMixin, table=True):
    """Allocate a payment journal to an open document (invoice/PO)."""

    __tablename__ = "payment_allocations"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    payment_journal_id: UUID = Field(foreign_key="journal_entries.id", index=True)
    target_source_type: str = Field(max_length=64)  # sales_document, purchase_order
    target_source_id: UUID = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    currency: str = Field(default="KES", max_length=3)


# Legacy bridge row (kept for T8/T9 compatibility + audit trail of domain events)
class FinancialEntry(BaseMixin, table=True):
    __tablename__ = "financial_entries"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    entry_type: FinancialEntryType = str_enum_col(FinancialEntryType.SALE_REVENUE)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    currency: str = Field(default="KES", max_length=3)
    source_type: str = Field(max_length=64)
    source_id: UUID = Field(index=True)
    party_id: UUID | None = Field(default=None)
    memo: str | None = Field(default=None, max_length=512)
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    journal_entry_id: UUID | None = Field(
        default=None, foreign_key="journal_entries.id", index=True
    )
