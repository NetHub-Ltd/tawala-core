"""Inventory domain — sole owner of stock state (T7 / M17).

Catalog Product = what it is. Inventory = how much and where.
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


class StockMovementType(StrEnum):
    RECEIVE = "receive"
    ISSUE = "issue"
    ADJUST = "adjust"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"


class StockLevel(BaseMixin, table=True):
    """Authoritative on-hand balance for a product at a location."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "product_id",
            "location_id",
            name="uq_stock_level_biz_product_location",
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    location_id: UUID = Field(foreign_key="locations.id", index=True)
    quantity_on_hand: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    quantity_reserved: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    version: int = Field(default=1, nullable=False)


class StockMovement(BaseMixin, table=True):
    """Append-oriented stock movement history (auditable ledger)."""

    __tablename__ = "stock_movements"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    location_id: UUID = Field(foreign_key="locations.id", index=True)
    movement_type: StockMovementType = str_enum_col(StockMovementType.ADJUST)
    quantity_delta: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    quantity_before: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    quantity_after: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    reason_code: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=512)
    actor_user_id: UUID | None = Field(default=None)
    request_id: UUID | None = Field(default=None)
    reference_type: str | None = Field(default=None, max_length=64)
    reference_id: UUID | None = Field(default=None)
    transfer_group_id: UUID | None = Field(default=None, index=True)
    occurred_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
