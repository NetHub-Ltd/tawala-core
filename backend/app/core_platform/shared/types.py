"""Shared Core types (SPEC Part E.1).

TenantContext and domain errors are defined here so every module
depends on one contract shape for tenancy and failures.

Authoritative contract reference: docs/architecture/CORE_CONTRACTS.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Authorized business context for a protected operation.

    Client-supplied business_id is never trusted without membership verification.
    """

    business_id: UUID
    actor_user_id: UUID
    membership_id: UUID
    request_id: UUID
    permissions: frozenset[str] = field(default_factory=frozenset)
    branch_id: UUID | None = None
    location_id: UUID | None = None


class DomainErrorCode(StrEnum):
    """Stable error categories for Core contracts (SPEC / DOMAIN_CONTRACTS)."""

    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    UNAUTHORIZED = "unauthorized"
    CONFLICT = "conflict"
    VALIDATION_FAILED = "validation_failed"
    ALREADY_PROCESSED = "already_processed"


class DomainError(Exception):
    """Base domain error for Core services."""

    def __init__(self, code: DomainErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
