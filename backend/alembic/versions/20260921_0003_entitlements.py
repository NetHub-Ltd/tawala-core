"""Capability catalog + business entitlements (T5).

Revision ID: 20260921_0003
Revises: 20260921_0002
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_0003"
down_revision: Union[str, None] = "20260921_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_capabilities_code"),
    )
    op.create_index("ix_capabilities_code", "capabilities", ["code"])

    op.create_table(
        "business_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("capability_code", sa.String(length=128), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id", "capability_code", name="uq_business_entitlement_biz_code"
        ),
    )
    op.create_index(
        "ix_business_entitlements_business_id", "business_entitlements", ["business_id"]
    )
    op.create_index(
        "ix_business_entitlements_capability_code",
        "business_entitlements",
        ["capability_code"],
    )

    # Tenant RLS on business_entitlements (capabilities are global catalog — no RLS)
    using = """(
        current_setting('app.rls_bypass', true) = 'on'
        OR (
            current_setting('app.current_business_id', true) <> ''
            AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
        )
    )"""
    op.execute("ALTER TABLE business_entitlements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE business_entitlements FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON business_entitlements FOR ALL USING {using} WITH CHECK {using}"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON business_entitlements")
    op.execute("ALTER TABLE business_entitlements NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE business_entitlements DISABLE ROW LEVEL SECURITY")
    op.drop_table("business_entitlements")
    op.drop_table("capabilities")
