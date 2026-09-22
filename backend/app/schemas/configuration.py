"""Business config schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConfigSet(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: dict[str, Any]


class ConfigRead(BaseModel):
    id: UUID
    business_id: UUID
    key: str
    value: dict[str, Any]
    updated_at: datetime

    model_config = {"from_attributes": True}
