"""Audit records (SPEC D.6 / M9) — append-only for normal roles."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class AuditRecord(BaseMixin, table=True):
    __tablename__ = "audit_records"

    business_id: UUID | None = Field(default=None, index=True)
    actor_user_id: UUID | None = Field(default=None, index=True)
    action: str = Field(max_length=128, index=True)
    resource_type: str = Field(max_length=64)
    resource_id: UUID | None = Field(default=None)
    outcome: AuditOutcome = str_enum_col(AuditOutcome.SUCCESS)
    request_id: UUID | None = Field(default=None)
    before: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    after: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    )
    reason: str | None = Field(default=None, max_length=512)
    occurred_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
