"""Identity models: User, Credential, Session (SPEC D.1)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class CredentialType(StrEnum):
    PASSWORD = "password"


class User(BaseMixin, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("phone", name="uq_users_phone"),
    )

    email: str | None = Field(default=None, max_length=320, index=True)
    phone: str | None = Field(default=None, max_length=32, index=True)
    display_name: str | None = Field(default=None, max_length=255)
    status: UserStatus = str_enum_col(UserStatus.ACTIVE)


class Credential(BaseMixin, table=True):
    __tablename__ = "credentials"

    user_id: UUID = Field(foreign_key="users.id", index=True)
    type: CredentialType = str_enum_col(CredentialType.PASSWORD)
    secret_hash: str = Field(sa_column=Column(Text, nullable=False))
    rotated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


class Session(BaseMixin, table=True):
    __tablename__ = "sessions"

    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    expires_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    user_agent: str | None = Field(default=None, max_length=512)
    ip: str | None = Field(default=None, max_length=64)
