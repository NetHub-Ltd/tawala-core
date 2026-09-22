"""Allow platform-scoped audit/events (business_id IS NULL) under RLS.

Revision ID: 20260922_0009
Revises: 20260921_0008
Create Date: 2026-09-22

Problem
-------
Baseline ``tenant_isolation`` policies use the same expression for USING and
WITH CHECK:

    rls_bypass = on
    OR (current_business_id <> '' AND business_id = current_business_id::uuid)

Auth register/login correctly write ``AuditRecord`` / ``DomainEvent`` with
``business_id=NULL`` (platform scope). Under a non-superuser role that policy
rejects the INSERT: NULL never equals a tenant UUID, and login has no bypass.

Ad-hoc ``set_tenant_guc(bypass=True)`` in IdentityService would paper over the
symptom and train domains to disable RLS. The durable fix is a deliberate
policy split:

* **USING (SELECT/UPDATE/DELETE visibility):** tenant rows by GUC match; platform
  rows (business_id IS NULL) only when ``rls_bypass`` is on (operators / tests).
* **WITH CHECK (INSERT/UPDATE):** same as USING, plus allow ``business_id IS NULL``
  so platform auth events can be recorded without a tenant context.

Applies only to ``audit_records`` and ``domain_events`` (nullable business_id).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260922_0009"
down_revision: Union[str, None] = "20260921_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("audit_records", "domain_events")

# Visibility: tenant match or operator bypass. Platform rows not tenant-visible.
_USING = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_business_id', true) <> ''
        AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
    )
)"""

# Writes: same as USING, plus platform-scoped rows (business_id IS NULL).
_CHECK = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR business_id IS NULL
    OR (
        current_setting('app.current_business_id', true) <> ''
        AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
    )
)"""


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"FOR ALL USING {_USING} WITH CHECK {_CHECK}"
        )


def downgrade() -> None:
    # Restore baseline single-expression policy (blocks platform inserts).
    baseline = """(
        current_setting('app.rls_bypass', true) = 'on'
        OR (
            current_setting('app.current_business_id', true) <> ''
            AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
        )
    )"""
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"FOR ALL USING {baseline} WITH CHECK {baseline}"
        )
