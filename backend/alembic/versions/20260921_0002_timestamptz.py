"""Convert all Core timestamp columns to TIMESTAMPTZ (timezone-aware).

Revision ID: 20260921_0002
Revises: 20260920_0001
Create Date: 2026-09-21

Existing naive values are interpreted as UTC via AT TIME ZONE 'UTC'.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0002"
down_revision: Union[str, None] = "20260920_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs that store timestamps in Core
_TS_COLUMNS: list[tuple[str, str]] = [
    # BaseMixin on all entity tables
    ("users", "created_at"),
    ("users", "updated_at"),
    ("users", "deleted_at"),
    ("credentials", "created_at"),
    ("credentials", "updated_at"),
    ("credentials", "deleted_at"),
    ("credentials", "rotated_at"),
    ("sessions", "created_at"),
    ("sessions", "updated_at"),
    ("sessions", "deleted_at"),
    ("sessions", "expires_at"),
    ("sessions", "revoked_at"),
    ("businesses", "created_at"),
    ("businesses", "updated_at"),
    ("businesses", "deleted_at"),
    ("branches", "created_at"),
    ("branches", "updated_at"),
    ("branches", "deleted_at"),
    ("locations", "created_at"),
    ("locations", "updated_at"),
    ("locations", "deleted_at"),
    ("memberships", "created_at"),
    ("memberships", "updated_at"),
    ("memberships", "deleted_at"),
    ("memberships", "invited_at"),
    ("memberships", "activated_at"),
    ("memberships", "revoked_at"),
    ("permissions", "created_at"),
    ("permissions", "updated_at"),
    ("permissions", "deleted_at"),
    ("roles", "created_at"),
    ("roles", "updated_at"),
    ("roles", "deleted_at"),
    ("scope_assignments", "created_at"),
    ("scope_assignments", "updated_at"),
    ("scope_assignments", "deleted_at"),
    ("parties", "created_at"),
    ("parties", "updated_at"),
    ("parties", "deleted_at"),
    ("party_business_links", "created_at"),
    ("party_business_links", "updated_at"),
    ("party_business_links", "deleted_at"),
    ("categories", "created_at"),
    ("categories", "updated_at"),
    ("categories", "deleted_at"),
    ("products", "created_at"),
    ("products", "updated_at"),
    ("products", "deleted_at"),
    ("services", "created_at"),
    ("services", "updated_at"),
    ("services", "deleted_at"),
    ("domain_events", "created_at"),
    ("domain_events", "updated_at"),
    ("domain_events", "deleted_at"),
    ("domain_events", "occurred_at"),
    ("outbox_entries", "created_at"),
    ("outbox_entries", "updated_at"),
    ("outbox_entries", "deleted_at"),
    ("outbox_entries", "next_attempt_at"),
    ("audit_records", "created_at"),
    ("audit_records", "updated_at"),
    ("audit_records", "deleted_at"),
    ("audit_records", "occurred_at"),
    ("business_configs", "created_at"),
    ("business_configs", "updated_at"),
    ("business_configs", "deleted_at"),
    ("idempotency_records", "created_at"),
    ("idempotency_records", "updated_at"),
    ("idempotency_records", "deleted_at"),
]


def upgrade() -> None:
    for table, column in _TS_COLUMNS:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" '
                f'ALTER COLUMN "{column}" TYPE TIMESTAMP WITH TIME ZONE '
                f"USING \"{column}\" AT TIME ZONE 'UTC'"
            )
        )


def downgrade() -> None:
    for table, column in _TS_COLUMNS:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" '
                f'ALTER COLUMN "{column}" TYPE TIMESTAMP WITHOUT TIME ZONE '
                f"USING \"{column}\" AT TIME ZONE 'UTC'"
            )
        )
