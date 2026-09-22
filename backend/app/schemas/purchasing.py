"""Purchasing API schemas (T9)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class POLineIn(BaseModel):
    product_id: UUID
    description: str = "Line"
    quantity_ordered: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseOrderCreate(BaseModel):
    party_id: UUID
    branch_id: UUID | None = None
    location_id: UUID | None = None
    notes: str | None = None
    currency: str = "KES"
    lines: list[POLineIn]


class PurchaseOrderRead(BaseModel):
    id: UUID
    business_id: UUID
    party_id: UUID
    status: str
    document_number: str
    location_id: UUID | None
    currency: str

    model_config = {"from_attributes": True}


class GRLineIn(BaseModel):
    purchase_order_line_id: UUID
    quantity: Decimal = Field(gt=0)


class GoodsReceiptCreate(BaseModel):
    purchase_order_id: UUID
    location_id: UUID
    notes: str | None = None
    lines: list[GRLineIn]


class GoodsReceiptRead(BaseModel):
    id: UUID
    business_id: UUID
    purchase_order_id: UUID
    location_id: UUID
    status: str
    document_number: str

    model_config = {"from_attributes": True}


class FinalizeBody(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=128)


class PurchasePaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = "cash"
    reference: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
