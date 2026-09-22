"""Identity request/response schemas (SPEC E / F.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserRegister(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_email_or_phone(self) -> UserRegister:
        if not self.email and not self.phone:
            raise ValueError("Either email or phone is required")
        return self


class UserLogin(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_identifier(self) -> UserLogin:
        if not self.email and not self.phone:
            raise ValueError("Either email or phone is required")
        return self


class UserRead(BaseModel):
    id: UUID
    email: str | None
    phone: str | None
    display_name: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead
