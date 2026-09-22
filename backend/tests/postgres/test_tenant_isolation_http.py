"""M12: Real PostgreSQL + HTTP tenant isolation (no FakeSession)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import select

from app.db.session import set_tenant_guc
from app.models.security import Membership, MembershipStatus

pytestmark = pytest.mark.asyncio


async def test_user_a_can_access_business_a(client, two_tenants):
    t = two_tenants
    r = await client.get(
        f"/api/v1/businesses/{t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(t["biz_a"])


async def test_user_a_cannot_access_business_b(client, two_tenants):
    t = two_tenants
    r = await client.get(
        f"/api/v1/businesses/{t['biz_b']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code in (403, 404), r.text


async def test_user_without_membership_cannot_access_business(client, two_tenants):
    t = two_tenants
    r = await client.get(
        f"/api/v1/businesses/{t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_none']}"},
    )
    assert r.status_code in (403, 404), r.text


async def test_idor_party_other_tenant(client, two_tenants):
    t = two_tenants
    r = await client.get(
        f"/api/v1/parties/{t['party_b']}?business_id={t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code in (403, 404), r.text


async def test_party_own_tenant_ok(client, two_tenants):
    t = two_tenants
    r = await client.get(
        f"/api/v1/parties/{t['party_a']}?business_id={t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code == 200, r.text


async def test_membership_revocation_blocks_access(client, two_tenants, db_session):
    t = two_tenants
    await set_tenant_guc(db_session, None, bypass=True)
    mem = await db_session.get(Membership, t["mem_a"])
    assert mem is not None
    mem.status = MembershipStatus.REVOKED
    mem.revoked_at = datetime.now(UTC)
    await db_session.commit()

    r = await client.get(
        f"/api/v1/businesses/{t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code in (403, 404), r.text


async def test_rls_hides_other_tenant_products(db_session, two_tenants):
    """Direct SQL with tenant GUC must not see other business products.

    Uses raw SQL counts so results are not influenced by the ORM identity map.
    Skips when the DB role is superuser (Postgres superusers bypass RLS even
    with FORCE ROW LEVEL SECURITY).
    """
    from sqlalchemy import text

    t = two_tenants

    conn = await db_session.connection()
    is_super = (
        await conn.execute(text("SELECT current_setting('is_superuser')"))
    ).scalar_one()
    if is_super == "on":
        pytest.skip("RLS is not enforced for PostgreSQL superusers")

    await set_tenant_guc(db_session, t["biz_a"], bypass=False)

    # Raw SQL — avoids identity-map leakage of Product instances seeded under bypass.
    conn = await db_session.connection()
    row_a = (
        await conn.execute(
            text("SELECT id FROM products WHERE id = CAST(:id AS uuid)"),
            {"id": str(t["prod_a"])},
        )
    ).scalar()
    row_b = (
        await conn.execute(
            text("SELECT id FROM products WHERE id = CAST(:id AS uuid)"),
            {"id": str(t["prod_b"])},
        )
    ).scalar()

    assert row_a is not None, "tenant product should be visible under matching GUC"
    assert row_b is None, "other-tenant product must be hidden by RLS"
