"""Party schemas (SPEC F.5)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PartyCreate(BaseModel):
    kind: str = Field(default="person")
    display_name: str = Field(min_length=1, max_length=255)
    primary_email: str | None = Field(default=None, max_length=320)
    primary_phone: str | None = Field(default=None, max_length=32)


class PartyRead(BaseModel):
    id: UUID
    kind: str
    display_name: str
    primary_email: str | None
    primary_phone: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartyLinkCreate(BaseModel):
    relationship: str = Field(default="customer")
    external_ref: str | None = Field(default=None, max_length=128)


class PartyLinkRead(BaseModel):
    id: UUID
    business_id: UUID
    party_id: UUID
    relationship: str
    status: str
    external_ref: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
