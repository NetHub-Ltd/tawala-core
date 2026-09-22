"""Party and business relationship links (SPEC D.4 / M7)."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class PartyKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"


class PartyRelationship(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    MEMBER = "member"
    OTHER = "other"


class LinkStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Party(BaseMixin, table=True):
    """Platform party identity — not tenant-owned alone; linked via PartyBusinessLink."""

    __tablename__ = "parties"

    kind: PartyKind = str_enum_col(PartyKind.PERSON)
    display_name: str = Field(max_length=255)
    primary_email: str | None = Field(default=None, max_length=320, index=True)
    primary_phone: str | None = Field(default=None, max_length=32, index=True)


class PartyBusinessLink(BaseMixin, table=True):
    __tablename__ = "party_business_links"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "party_id",
            "relationship",
            name="uq_party_business_relationship",
        ),
    )

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    party_id: UUID = Field(foreign_key="parties.id", index=True)
    relationship: PartyRelationship = str_enum_col(PartyRelationship.CUSTOMER)
    status: LinkStatus = str_enum_col(LinkStatus.ACTIVE)
    external_ref: str | None = Field(default=None, max_length=128)
