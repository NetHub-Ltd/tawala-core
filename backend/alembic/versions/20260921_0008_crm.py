"""CRM customer profiles, notes, activity (T11).

Revision ID: 20260921_0008
Revises: 20260921_0007
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0008"
down_revision: Union[str, None] = "20260921_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_business_id', true) <> ''
        AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
    )
)"""


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} FOR ALL USING {_RLS} WITH CHECK {_RLS}"
    )


def upgrade() -> None:
    op.create_table(
        "customer_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("credit_status", sa.String(32), nullable=False),
        sa.Column("credit_limit", sa.Numeric(18, 4), nullable=False),
        sa.Column("segment", sa.String(64), nullable=True),
        sa.Column("tags", sa.String(512), nullable=True),
        sa.Column("preferred_branch_id", sa.Uuid(), nullable=True),
        sa.Column("notes_summary", sa.String(1024), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"]),
        sa.ForeignKeyConstraint(["preferred_branch_id"], ["branches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id", "party_id", name="uq_customer_profile_biz_party"
        ),
    )
    op.create_index("ix_customer_profiles_business_id", "customer_profiles", ["business_id"])
    op.create_index("ix_customer_profiles_party_id", "customer_profiles", ["party_id"])

    op.create_table(
        "customer_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_notes_business_id", "customer_notes", ["business_id"])
    op.create_index("ix_customer_notes_party_id", "customer_notes", ["party_id"])

    op.create_table(
        "customer_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(512), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_activities_business_id", "customer_activities", ["business_id"])
    op.create_index("ix_customer_activities_party_id", "customer_activities", ["party_id"])

    for t in ("customer_profiles", "customer_notes", "customer_activities"):
        _rls(t)


def downgrade() -> None:
    for t in ("customer_activities", "customer_notes", "customer_profiles"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
        op.drop_table(t)
