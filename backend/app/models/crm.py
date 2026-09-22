"""CRM — business-scoped customer intelligence on Party identity (T11).

Does not duplicate Party. Does not own sales or accounting truth.
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


class CreditStatus(StrEnum):
    """Authoritative credit state lives on CustomerProfile (CRM), not Accounting."""

    GOOD = "good"
    WATCH = "watch"
    BLOCKED = "blocked"
    NONE = "none"


class CustomerProfile(BaseMixin, table=True):
    """Per-business CRM extension of a Party (customer relationship)."""

    __tablename__ = "customer_profiles"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "party_id", name="uq_customer_profile_biz_party"
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    party_id: UUID = Field(foreign_key="parties.id", index=True)
    credit_status: CreditStatus = str_enum_col(CreditStatus.NONE)
    credit_limit: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    # Relationship metadata (not identity)
    segment: str | None = Field(default=None, max_length=64)
    tags: str | None = Field(default=None, max_length=512)  # comma-separated simple tags
    preferred_branch_id: UUID | None = Field(default=None, foreign_key="branches.id")
    notes_summary: str | None = Field(default=None, max_length=1024)


class CustomerNote(BaseMixin, table=True):
    __tablename__ = "customer_notes"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    party_id: UUID = Field(foreign_key="parties.id", index=True)
    body: str = Field(max_length=4000)
    actor_user_id: UUID | None = Field(default=None)


class CustomerActivity(BaseMixin, table=True):
    """CRM-side activity log (notes, credit changes). Sales history is queried from Sales."""

    __tablename__ = "customer_activities"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    party_id: UUID = Field(foreign_key="parties.id", index=True)
    activity_type: str = Field(max_length=64)  # note_added, credit_updated, profile_updated
    summary: str = Field(max_length=512)
    actor_user_id: UUID | None = Field(default=None)
    occurred_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
