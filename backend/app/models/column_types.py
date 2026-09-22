"""SQLModel column helpers — keep Python enums as VARCHAR in PostgreSQL.

All Core migrations store status/type/kind as ``String(32)``, not native PG
ENUMs. Binding StrEnum fields with ``native_enum=False`` (via String columns)
keeps the ORM aligned with SQLModel models and Alembic schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import Column, String
from sqlmodel import Field

E = TypeVar("E", bound=StrEnum)


def str_enum_col(default: E, *, max_length: int = 32, index: bool = False) -> Any:
    """Field for a StrEnum persisted as VARCHAR (SQLModel-native, migration-aligned)."""
    return Field(
        default=default,
        sa_column=Column(String(max_length), nullable=False, index=index),
    )
