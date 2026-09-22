"""Idempotency keys for retried Core commands (SPEC / Domain Contracts / #262)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field

from app.models.base import BaseMixin


class IdempotencyRecord(BaseMixin, table=True):
    """Stores first successful result for an idempotency key within a scope.

    scope:
      - ``platform`` for user registration
      - business UUID string for business-scoped commands
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )

    scope: str = Field(max_length=64, index=True)
    key: str = Field(max_length=128, index=True)
    operation: str = Field(max_length=64)
    response_status: int = Field(default=200)
    response_body: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    )
    resource_id: UUID | None = Field(default=None)
