"""RLS GUCs must survive intermediate session.commit() within one request (#292).

NullPool releases the connection on commit; tenant intent is stored on
session.info and re-applied via after_begin.

RLS visibility assertions require a **non-superuser** DB role (FORCE RLS does
not bind superusers). CI uses ``tawala_app`` for that reason.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import set_tenant_guc
from app.models.catalog import Product


async def _is_superuser(session) -> bool:
    conn = await session.connection()
    val = (await conn.execute(text("SELECT current_setting('is_superuser')"))).scalar_one()
    return val == "on"


@pytest.mark.asyncio
async def test_rls_guc_survives_commit_then_second_query(db_session, two_tenants):
    """create product → commit → GUC restored; other tenant hidden by RLS."""
    if await _is_superuser(db_session):
        pytest.skip(
            "Postgres superusers bypass RLS (even FORCE). "
            "CI must run tests as non-superuser tawala_app."
        )

    t = two_tenants
    biz_a = t["biz_a"]

    await set_tenant_guc(db_session, biz_a, bypass=False)

    prod = Product(
        id=uuid4(),
        business_id=biz_a,
        name=f"GUC-survive-{uuid4().hex[:8]}",
        sku=f"SKU-{uuid4().hex[:6]}",
        unit="ea",
    )
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)

    conn = await db_session.connection()
    row = (
        await conn.execute(
            text("SELECT current_setting('app.current_business_id', true)")
        )
    ).scalar_one()
    assert row == str(biz_a), f"GUC lost after commit; got {row!r}"

    own = (
        await conn.execute(
            text("SELECT id FROM products WHERE id = CAST(:id AS uuid)"),
            {"id": str(prod.id)},
        )
    ).scalar()
    other = (
        await conn.execute(
            text("SELECT id FROM products WHERE id = CAST(:id AS uuid)"),
            {"id": str(t["prod_b"])},
        )
    ).scalar()
    assert own is not None, "own product must remain visible under matching GUC"
    assert other is None, "other-tenant product must stay hidden by RLS after commit"


@pytest.mark.asyncio
async def test_rls_guc_restored_after_commit(db_session, two_tenants):
    """session.info tenant_guc re-applied on next transaction after COMMIT."""
    t = two_tenants
    await set_tenant_guc(db_session, t["biz_a"], bypass=False)
    conn = await db_session.connection()
    await conn.execute(text("SELECT 1"))
    await db_session.commit()

    conn = await db_session.connection()
    val = (
        await conn.execute(
            text("SELECT current_setting('app.current_business_id', true)")
        )
    ).scalar_one()
    assert val == str(t["biz_a"]), f"expected tenant GUC after commit, got {val!r}"
