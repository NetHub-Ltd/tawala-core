"""Inventory API schemas (T7)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class StockMutate(BaseModel):
    product_id: UUID
    location_id: UUID
    quantity: Decimal = Field(gt=0)
    note: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockAdjust(BaseModel):
    product_id: UUID
    location_id: UUID
    quantity_on_hand: Decimal = Field(ge=0)
    reason_code: str | None = None
    note: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockTransfer(BaseModel):
    product_id: UUID
    from_location_id: UUID
    to_location_id: UUID
    quantity: Decimal = Field(gt=0)
    note: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class StockLevelRead(BaseModel):
    id: UUID
    business_id: UUID
    product_id: UUID
    location_id: UUID
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    version: int

    model_config = {"from_attributes": True}


class StockMovementRead(BaseModel):
    id: UUID
    business_id: UUID
    product_id: UUID
    location_id: UUID
    movement_type: str
    quantity_delta: Decimal
    quantity_before: Decimal
    quantity_after: Decimal
    reason_code: str | None
    note: str | None
    transfer_group_id: UUID | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class StockTransferRead(BaseModel):
    out_movement: StockMovementRead
    in_movement: StockMovementRead
