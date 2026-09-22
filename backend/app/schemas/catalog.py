"""Catalog schemas — reject stock quantity fields (SPEC M8)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    category_id: UUID | None = None
    unit: str = Field(default="ea", max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def reject_stock_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"quantity", "stock", "on_hand", "qty"}
            present = forbidden.intersection(data.keys())
            if present:
                raise ValueError(
                    f"Catalog products must not include stock fields: {sorted(present)}"
                )
        return data


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = None
    barcode: str | None = None
    category_id: UUID | None = None
    unit: str | None = None
    status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_stock_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"quantity", "stock", "on_hand", "qty"}
            present = forbidden.intersection(data.keys())
            if present:
                raise ValueError(
                    f"Catalog products must not include stock fields: {sorted(present)}"
                )
        return data


class ProductRead(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    sku: str | None
    barcode: str | None
    category_id: UUID | None
    unit: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=128)


class ServiceRead(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    code: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None


class CategoryRead(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    parent_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
