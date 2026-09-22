"""Capability catalog and per-business entitlements (T5 / M15).

Capabilities describe product features/limits. Entitlements grant them to a
Business. This is orthogonal to RBAC permissions (user may-do).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class CapabilityKind(StrEnum):
    MODULE = "module"
    LIMIT = "limit"
    FLAG = "flag"


class Capability(BaseMixin, table=True):
    """Global catalog of product capabilities (not tenant-scoped)."""

    __tablename__ = "capabilities"
    __table_args__ = (UniqueConstraint("code", name="uq_capabilities_code"),)

    code: str = Field(max_length=128, index=True)
    kind: CapabilityKind = str_enum_col(CapabilityKind.MODULE)
    description: str | None = Field(default=None, max_length=512)


class BusinessEntitlement(BaseMixin, table=True):
    """Grant of a capability to one Business (optional limit + validity window)."""

    __tablename__ = "business_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "capability_code",
            name="uq_business_entitlement_biz_code",
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    capability_code: str = Field(max_length=128, index=True)
    limit_value: int | None = Field(default=None)
    source: str | None = Field(default=None, max_length=64)
    valid_from: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    valid_until: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
