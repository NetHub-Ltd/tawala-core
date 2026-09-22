"""Sales API schemas (T8)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SalesLineIn(BaseModel):
    product_id: UUID | None = None
    description: str = "Line"
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class SalesDocumentCreate(BaseModel):
    document_type: str
    party_id: UUID | None = None
    branch_id: UUID | None = None
    location_id: UUID | None = None
    notes: str | None = None
    source_document_id: UUID | None = None
    lines: list[SalesLineIn]
    currency: str = "KES"


class SalesDocumentRead(BaseModel):
    id: UUID
    business_id: UUID
    document_type: str
    status: str
    document_number: str
    party_id: UUID | None
    branch_id: UUID | None
    location_id: UUID | None
    source_document_id: UUID | None
    currency: str

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = "cash"
    reference: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class FinalizeBody(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=128)
