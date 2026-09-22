"""Entitlement API schemas (T5)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EntitlementGrant(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    limit_value: int | None = None
    source: str | None = Field(default="manual", max_length=64)


class EntitlementRead(BaseModel):
    id: UUID
    business_id: UUID
    capability_code: str
    limit_value: int | None
    source: str | None
    valid_from: datetime | None
    valid_until: datetime | None

    model_config = {"from_attributes": True}


class CapabilityRead(BaseModel):
    id: UUID
    code: str
    kind: str
    description: str | None

    model_config = {"from_attributes": True}
