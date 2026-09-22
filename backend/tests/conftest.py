"""Shared fixtures — real PostgreSQL only. No FakeSession.

Requires DB credentials (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME) and ENVIRONMENT=test.
CI provides a Postgres service and sets those variables.

Note: migration setup is a *sync* session-scoped fixture so it does not
conflict with pytest-asyncio's default function-scoped event loop.
Pytest-asyncio options live only in pyproject.toml (single source of truth).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from alembic import command
from app.core_platform.shared.settings import clear_settings_cache, get_settings
from app.db.session import dispose_engine, get_session_factory, reset_engine, set_tenant_guc
from app.main import app


def _has_db_credentials() -> bool:
    return all(
        os.environ.get(k, "").strip()
        for k in ("DB_HOST", "DB_USER", "DB_NAME")
    ) and os.environ.get("DB_PASSWORD") is not None


@pytest.fixture(scope="session")
def database_url_sync() -> str:
    """Sync DSN for Alembic (built from credentials only)."""
    if not _has_db_credentials():
        pytest.skip("DB_HOST/DB_USER/DB_PASSWORD/DB_NAME not set — PostgreSQL required")
    os.environ["ENVIRONMENT"] = "test"
    clear_settings_cache()
    reset_engine()
    return get_settings().require_database_url_sync()


@pytest.fixture(scope="session")
def prepared_database(database_url_sync: str) -> None:
    """Ensure schema is at head (sync — avoids ScopeMismatch).

    CI migrates as superuser before pytest, then runs tests as non-superuser
    ``tawala_app`` so RLS is enforced. Local runs may migrate here if the
    configured user can DDL.
    """
    clear_settings_cache()
    reset_engine()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url_sync)
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        # Non-superuser app role cannot create tables; schema must already exist.
        msg = str(exc).lower()
        if "permission" in msg or "must be owner" in msg:
            return
        raise


@pytest_asyncio.fixture
async def db_session(prepared_database: None) -> AsyncGenerator[AsyncSession, None]:
    # Fresh engine on this test's event loop (avoids "Future attached to different loop").
    await dispose_engine()
    reset_engine()
    factory = get_session_factory()
    assert factory is not None
    async with factory() as session:
        await set_tenant_guc(session, business_id=None, bypass=True)
        yield session
        await session.rollback()
    await dispose_engine()


@pytest_asyncio.fixture
async def client(prepared_database: None) -> AsyncGenerator[AsyncClient, None]:
    # Ensure app DB deps use an engine bound to this loop.
    await dispose_engine()
    reset_engine()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()


@pytest_asyncio.fixture
async def two_tenants(db_session: AsyncSession, client: AsyncClient) -> dict:
    """Seed two businesses, three users, parties, products; return tokens + ids."""
    from app.core_platform.identity.password import hash_password
    from app.core_platform.security.service import RoleService
    from app.models.catalog import Product
    from app.models.identity import Credential, CredentialType, User, UserStatus
    from app.models.organization import Business, BusinessStatus
    from app.models.parties import (
        LinkStatus,
        Party,
        PartyBusinessLink,
        PartyKind,
        PartyRelationship,
    )
    from app.models.security import Membership, MembershipStatus

    await set_tenant_guc(db_session, None, bypass=True)

    biz_a = Business(id=uuid4(), name="Business A", status=BusinessStatus.ACTIVE)
    biz_b = Business(id=uuid4(), name="Business B", status=BusinessStatus.ACTIVE)
    db_session.add_all([biz_a, biz_b])

    user_a = User(
        id=uuid4(), email=f"a-{uuid4().hex[:8]}@example.com", status=UserStatus.ACTIVE
    )
    user_b = User(
        id=uuid4(), email=f"b-{uuid4().hex[:8]}@example.com", status=UserStatus.ACTIVE
    )
    user_none = User(
        id=uuid4(),
        email=f"none-{uuid4().hex[:8]}@example.com",
        status=UserStatus.ACTIVE,
    )
    db_session.add_all([user_a, user_b, user_none])
    # Credentials reference users through a scalar FK; flush the parent rows
    # before the executemany credential insert.
    await db_session.flush()

    pwd = "TestPass123!"
    for u in (user_a, user_b, user_none):
        db_session.add(
            Credential(
                id=uuid4(),
                user_id=u.id,
                type=CredentialType.PASSWORD,
                secret_hash=hash_password(pwd),
            )
        )

    mem_a = Membership(
        id=uuid4(),
        business_id=biz_a.id,
        user_id=user_a.id,
        status=MembershipStatus.ACTIVE,
        activated_at=datetime.now(UTC),
    )
    mem_b = Membership(
        id=uuid4(),
        business_id=biz_b.id,
        user_id=user_b.id,
        status=MembershipStatus.ACTIVE,
        activated_at=datetime.now(UTC),
    )
    db_session.add_all([mem_a, mem_b])
    await db_session.flush()

    # Capture scalar PKs once after flush. Always use these plain UUIDs — never
    # re-read ORM attributes after set_tenant_guc / commit (async safety).
    biz_a_id = biz_a.id
    biz_b_id = biz_b.id
    mem_a_id = mem_a.id
    mem_b_id = mem_b.id
    user_a_id = user_a.id
    user_b_id = user_b.id
    email_a = user_a.email
    email_b = user_b.email
    email_none = user_none.email

    roles = RoleService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    await roles.bootstrap_owner(biz_a_id, mem_a_id)
    await set_tenant_guc(db_session, None, bypass=True)
    await roles.bootstrap_owner(biz_b_id, mem_b_id)

    await set_tenant_guc(db_session, None, bypass=True)
    party_a_id = uuid4()
    party_b_id = uuid4()
    prod_a_id = uuid4()
    prod_b_id = uuid4()
    party_a = Party(id=party_a_id, kind=PartyKind.PERSON, display_name="Party A")
    party_b = Party(id=party_b_id, kind=PartyKind.PERSON, display_name="Party B")
    db_session.add_all([party_a, party_b])
    db_session.add(
        PartyBusinessLink(
            id=uuid4(),
            business_id=biz_a_id,
            party_id=party_a_id,
            relationship=PartyRelationship.CUSTOMER,
            status=LinkStatus.ACTIVE,
        )
    )
    db_session.add(
        PartyBusinessLink(
            id=uuid4(),
            business_id=biz_b_id,
            party_id=party_b_id,
            relationship=PartyRelationship.CUSTOMER,
            status=LinkStatus.ACTIVE,
        )
    )
    prod_a = Product(
        id=prod_a_id, business_id=biz_a_id, name="Product A", sku=f"A-{uuid4().hex[:6]}"
    )
    prod_b = Product(
        id=prod_b_id, business_id=biz_b_id, name="Product B", sku=f"B-{uuid4().hex[:6]}"
    )
    db_session.add_all([prod_a, prod_b])

    await db_session.commit()

    # T5: product paths require module.catalog entitlement (deny-by-default)
    from app.core_platform.entitlements.service import EntitlementService

    await set_tenant_guc(db_session, None, bypass=True)
    ent = EntitlementService(db_session)
    await ent.ensure_catalog_seeded()
    await ent.grant(biz_a_id, "module.catalog", source="test")
    await ent.grant(biz_b_id, "module.catalog", source="test")

    async def _login(email: str) -> str:
        r = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": pwd}
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    return {
        "biz_a": biz_a_id,
        "biz_b": biz_b_id,
        "party_a": party_a_id,
        "party_b": party_b_id,
        "prod_a": prod_a_id,
        "prod_b": prod_b_id,
        "mem_a": mem_a_id,
        "token_a": await _login(email_a),
        "token_b": await _login(email_b),
        "token_none": await _login(email_none),
        "email_a": email_a,
        "session": db_session,
    }
