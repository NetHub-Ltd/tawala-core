"""CRM API schemas (T11)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileUpdate(BaseModel):
    credit_status: str | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0)
    segment: str | None = None
    tags: str | None = None
    preferred_branch_id: UUID | None = None
    notes_summary: str | None = None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ProfileRead(BaseModel):
    id: UUID
    business_id: UUID
    party_id: UUID
    credit_status: str
    credit_limit: Decimal
    segment: str | None
    tags: str | None
    notes_summary: str | None

    model_config = {"from_attributes": True}
