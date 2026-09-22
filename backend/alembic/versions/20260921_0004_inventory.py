"""Inventory stock_levels + stock_movements (T7).

Revision ID: 20260921_0004
Revises: 20260921_0003
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0004"
down_revision: Union[str, None] = "20260921_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_USING = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_business_id', true) <> ''
        AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
    )
)"""


def upgrade() -> None:
    op.create_table(
        "stock_levels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_reserved", sa.Numeric(18, 4), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "product_id",
            "location_id",
            name="uq_stock_level_biz_product_location",
        ),
        sa.CheckConstraint(
            "quantity_on_hand >= 0", name="ck_stock_levels_on_hand_nonneg"
        ),
        sa.CheckConstraint(
            "quantity_reserved >= 0", name="ck_stock_levels_reserved_nonneg"
        ),
    )
    op.create_index("ix_stock_levels_business_id", "stock_levels", ["business_id"])
    op.create_index("ix_stock_levels_product_id", "stock_levels", ["product_id"])
    op.create_index("ix_stock_levels_location_id", "stock_levels", ["location_id"])

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_before", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("transfer_group_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_movements_business_id", "stock_movements", ["business_id"])
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index("ix_stock_movements_location_id", "stock_movements", ["location_id"])
    op.create_index(
        "ix_stock_movements_transfer_group_id", "stock_movements", ["transfer_group_id"]
    )

    for table in ("stock_levels", "stock_movements"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            f"USING {_RLS_USING} WITH CHECK {_RLS_USING}"
        )


def downgrade() -> None:
    for table in ("stock_movements", "stock_levels"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("stock_movements")
    op.drop_table("stock_levels")
