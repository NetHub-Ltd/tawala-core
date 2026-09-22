"""Shared SQLModel base with audit / soft-delete metadata.

All Core tables extend :class:`BaseMixin` so identity, tenancy, and domain
models share the same primary key and lifecycle columns.

**Time policy:** every timestamp is timezone-aware UTC (``TIMESTAMPTZ`` in PostgreSQL).

Use ``sa_type=DateTime(timezone=True)`` (not a shared ``Column`` instance) so each
subclass table gets its own column object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime for all Core timestamp fields."""
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """Deprecated alias — returns aware UTC (kept for older imports)."""
    return utc_now()


def _utcnow() -> datetime:
    return utc_now()


class BaseMixin(SQLModel):
    """Default metadata fields for every Core entity.

    Attributes:
        id: UUID primary key.
        created_at: Row creation time (timezone-aware UTC).
        updated_at: Last update time (timezone-aware UTC).
        deleted_at: Soft-delete timestamp; null means active.
        deleted_by: User who soft-deleted the row, if any.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    deleted_by: UUID | None = Field(default=None, nullable=True)

    def touch(self) -> None:
        """Bump ``updated_at`` to now (call before commit on updates)."""
        self.updated_at = utc_now()

    def soft_delete(self, *, by_user_id: UUID | None = None) -> None:
        """Mark row as soft-deleted without removing it."""
        self.deleted_at = utc_now()
        self.deleted_by = by_user_id
        self.touch()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
