"""Membership, roles, permissions, scope (SPEC D.3 / M6)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class MembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class Membership(BaseMixin, table=True):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "user_id", name="uq_membership_business_user"
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    status: MembershipStatus = str_enum_col(MembershipStatus.ACTIVE)
    invited_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    activated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


class Permission(BaseMixin, table=True):
    __tablename__ = "permissions"

    code: str = Field(max_length=128, unique=True, index=True)
    description: str | None = Field(default=None, max_length=512)


class Role(BaseMixin, table=True):
    __tablename__ = "roles"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    name: str = Field(max_length=128)
    is_system: bool = Field(default=False)


class RolePermission(SQLModel, table=True):
    """Join table — composite PK; still uses SQLModel."""

    __tablename__ = "role_permissions"

    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)
    permission_id: UUID = Field(foreign_key="permissions.id", primary_key=True)


class MembershipRole(SQLModel, table=True):
    __tablename__ = "membership_roles"

    membership_id: UUID = Field(foreign_key="memberships.id", primary_key=True)
    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)


class ScopeAssignment(BaseMixin, table=True):
    __tablename__ = "scope_assignments"

    membership_id: UUID = Field(foreign_key="memberships.id", index=True)
    branch_id: UUID | None = Field(default=None, foreign_key="branches.id")
    location_id: UUID | None = Field(default=None, foreign_key="locations.id")
