"""Catalog identity only — Product / Service / Category (SPEC D.5 / M8).

FORBIDDEN: quantity, stock, on_hand columns. Inventory is a separate domain.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlmodel import Field

from app.models.base import BaseMixin
from app.models.column_types import str_enum_col


class CatalogStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Category(BaseMixin, table=True):
    __tablename__ = "categories"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    name: str = Field(max_length=255)
    parent_id: UUID | None = Field(default=None, foreign_key="categories.id")


class Product(BaseMixin, table=True):
    __tablename__ = "products"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    name: str = Field(max_length=255)
    sku: str | None = Field(default=None, max_length=128, index=True)
    barcode: str | None = Field(default=None, max_length=128)
    category_id: UUID | None = Field(default=None, foreign_key="categories.id")
    unit: str = Field(default="ea", max_length=32)
    status: CatalogStatus = str_enum_col(CatalogStatus.ACTIVE)
    # NO quantity / stock / on_hand — enforced by schema tests and SPEC


class Service(BaseMixin, table=True):
    __tablename__ = "services"

    business_id: UUID = Field(foreign_key="businesses.id", index=True)
    name: str = Field(max_length=255)
    code: str | None = Field(default=None, max_length=128)
    status: CatalogStatus = str_enum_col(CatalogStatus.ACTIVE)
