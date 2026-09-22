"""Baseline schema matching app.models (SQLModel).

Revision ID: 20260920_0001
Revises:
Create Date: 2026-09-20

This revision is the frozen DDL snapshot of SQLModel tables under app.models.
Apply with: alembic upgrade head
Do not use SQLModel.metadata.create_all at application startup.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260920_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_TABLES = (
    "memberships",
    "roles",
    "branches",
    "locations",
    "party_business_links",
    "categories",
    "products",
    "services",
    "business_configs",
    "audit_records",
    "domain_events",
)


def _mixin_cols():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    # --- identity ---
    op.create_table(
        "users",
        *_mixin_cols(),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "credentials",
        *_mixin_cols(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_credentials_user_id", "credentials", ["user_id"])

    op.create_table(
        "sessions",
        *_mixin_cols(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # --- organization ---
    op.create_table(
        "businesses",
        *_mixin_cols(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_businesses_slug", "businesses", ["slug"])

    op.create_table(
        "branches",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index("ix_branches_business_id", "branches", ["business_id"])

    op.create_table(
        "locations",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
    )
    op.create_index("ix_locations_business_id", "locations", ["business_id"])
    op.create_index("ix_locations_branch_id", "locations", ["branch_id"])

    # --- security ---
    op.create_table(
        "memberships",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("business_id", "user_id", name="uq_membership_business_user"),
    )
    op.create_index("ix_memberships_business_id", "memberships", ["business_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "permissions",
        *_mixin_cols(),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])

    op.create_table(
        "roles",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index("ix_roles_business_id", "roles", ["business_id"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "membership_roles",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("membership_id", "role_id"),
    )

    op.create_table(
        "scope_assignments",
        *_mixin_cols(),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
    )
    op.create_index(
        "ix_scope_assignments_membership_id", "scope_assignments", ["membership_id"]
    )

    # --- parties ---
    op.create_table(
        "parties",
        *_mixin_cols(),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("primary_email", sa.String(length=320), nullable=True),
        sa.Column("primary_phone", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_parties_primary_email", "parties", ["primary_email"])
    op.create_index("ix_parties_primary_phone", "parties", ["primary_phone"])

    op.create_table(
        "party_business_links",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"]),
        sa.UniqueConstraint(
            "business_id",
            "party_id",
            "relationship",
            name="uq_party_business_relationship",
        ),
    )
    op.create_index(
        "ix_party_business_links_business_id", "party_business_links", ["business_id"]
    )
    op.create_index(
        "ix_party_business_links_party_id", "party_business_links", ["party_id"]
    )

    # --- catalog ---
    op.create_table(
        "categories",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
    )
    op.create_index("ix_categories_business_id", "categories", ["business_id"])

    op.create_table(
        "products",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )
    op.create_index("ix_products_business_id", "products", ["business_id"])
    op.create_index("ix_products_sku", "products", ["sku"])

    op.create_table(
        "services",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index("ix_services_business_id", "services", ["business_id"])

    # --- events / audit / config / idempotency ---
    op.create_table(
        "domain_events",
        *_mixin_cols(),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
    )
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_business_id", "domain_events", ["business_id"])
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])

    op.create_table(
        "outbox_entries",
        *_mixin_cols(),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["domain_events.id"]),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_outbox_entries_event_id", "outbox_entries", ["event_id"])

    op.create_table(
        "audit_records",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column(
            "before",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "after",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_records_business_id", "audit_records", ["business_id"])
    op.create_index("ix_audit_records_actor_user_id", "audit_records", ["actor_user_id"])
    op.create_index("ix_audit_records_action", "audit_records", ["action"])

    op.create_table(
        "business_configs",
        *_mixin_cols(),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "value",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.UniqueConstraint("business_id", "key", name="uq_business_config_key"),
    )
    op.create_index(
        "ix_business_configs_business_id", "business_configs", ["business_id"]
    )

    op.create_table(
        "idempotency_records",
        *_mixin_cols(),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column(
            "response_body",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_records_scope", "idempotency_records", ["scope"])
    op.create_index("ix_idempotency_records_key", "idempotency_records", ["key"])

    # --- RLS (Postgres policies; not part of SQLModel field definitions) ---
    for table in _TENANT_TABLES:
        if table == "memberships":
            using = """(
                current_setting('app.rls_bypass', true) = 'on'
                OR (
                    current_setting('app.current_business_id', true) <> ''
                    AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
                )
                OR (
                    current_setting('app.current_user_id', true) <> ''
                    AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                )
            )"""
        else:
            using = """(
                current_setting('app.rls_bypass', true) = 'on'
                OR (
                    current_setting('app.current_business_id', true) <> ''
                    AND business_id = NULLIF(current_setting('app.current_business_id', true), '')::uuid
                )
            )"""
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL USING {using} WITH CHECK {using}"
        )


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for name in (
        "idempotency_records",
        "business_configs",
        "audit_records",
        "outbox_entries",
        "domain_events",
        "services",
        "products",
        "categories",
        "party_business_links",
        "parties",
        "scope_assignments",
        "membership_roles",
        "role_permissions",
        "roles",
        "permissions",
        "memberships",
        "locations",
        "branches",
        "businesses",
        "sessions",
        "credentials",
        "users",
    ):
        op.drop_table(name)
