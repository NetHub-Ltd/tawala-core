"""Accounting Core: COA, journals, allocations (T10).

Revision ID: 20260921_0007
Revises: 20260921_0006
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0007"
down_revision: Union[str, None] = "20260921_0006"
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
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "code", name="uq_account_biz_code"),
    )
    op.create_index("ix_accounts_business_id", "accounts", ["business_id"])
    op.create_index("ix_accounts_code", "accounts", ["code"])

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("entry_number", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("domain_entry_type", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("memo", sa.String(512), nullable=True),
        sa.Column("party_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverses_entry_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_by_entry_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["reverses_entry_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id", "entry_number", name="uq_journal_biz_number"
        ),
    )
    op.create_index("ix_journal_entries_business_id", "journal_entries", ["business_id"])
    op.create_index("ix_journal_entries_source_id", "journal_entries", ["source_id"])

    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("debit", sa.Numeric(18, 4), nullable=False),
        sa.Column("credit", sa.Numeric(18, 4), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=True),
        sa.Column("tax_code", sa.String(32), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("memo", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(debit >= 0 AND credit >= 0) AND NOT (debit > 0 AND credit > 0)",
            name="ck_journal_line_debit_xor_credit",
        ),
    )
    op.create_index("ix_journal_lines_journal_entry_id", "journal_lines", ["journal_entry_id"])
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("payment_journal_id", sa.Uuid(), nullable=False),
        sa.Column("target_source_type", sa.String(64), nullable=False),
        sa.Column("target_source_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["payment_journal_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_allocations_payment_journal_id",
        "payment_allocations",
        ["payment_journal_id"],
    )
    op.create_index(
        "ix_payment_allocations_target_source_id",
        "payment_allocations",
        ["target_source_id"],
    )

    # Link legacy financial_entries to journals
    op.add_column(
        "financial_entries",
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_financial_entries_journal",
        "financial_entries",
        "journal_entries",
        ["journal_entry_id"],
        ["id"],
    )
    op.create_index(
        "ix_financial_entries_journal_entry_id",
        "financial_entries",
        ["journal_entry_id"],
    )

    for t in ("accounts", "journal_entries", "journal_lines", "payment_allocations"):
        _rls(t)


def downgrade() -> None:
    op.drop_index("ix_financial_entries_journal_entry_id", "financial_entries")
    op.drop_constraint("fk_financial_entries_journal", "financial_entries", type_="foreignkey")
    op.drop_column("financial_entries", "journal_entry_id")
    for t in (
        "payment_allocations",
        "journal_lines",
        "journal_entries",
        "accounts",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
        op.drop_table(t)
