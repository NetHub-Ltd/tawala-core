"""Business configuration key/value (SPEC D.6)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field

from app.models.base import BaseMixin


class BusinessConfig(BaseMixin, table=True):
    __tablename__ = "business_configs"
    __table_args__ = (
        UniqueConstraint("business_id", "key", name="uq_business_config_key"),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    key: str = Field(max_length=128)
    value: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    )
