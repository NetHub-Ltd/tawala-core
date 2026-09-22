"""Organization schemas (SPEC F.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=64)


class BusinessRead(BaseModel):
    id: UUID
    name: str
    slug: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=64)


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)


class BranchRead(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    code: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="other")


class LocationRead(BaseModel):
    id: UUID
    business_id: UUID
    branch_id: UUID
    name: str
    kind: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
