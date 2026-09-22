"""Audit response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditRecordRead(BaseModel):
    id: UUID
    business_id: UUID | None
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    outcome: str
    occurred_at: datetime
    reason: str | None = None

    model_config = {"from_attributes": True}
