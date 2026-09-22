"""M13: Scope enforcement via real PostgreSQL + HTTP."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.session import set_tenant_guc
from app.models.organization import Branch, BranchStatus
from app.models.security import ScopeAssignment

pytestmark = pytest.mark.asyncio


async def test_empty_scope_allows_branch_query_param(client, two_tenants, db_session):
    """Owner-style membership with no ScopeAssignment may pass any branch_id."""
    t = two_tenants
    await set_tenant_guc(db_session, None, bypass=True)
    branch = Branch(
        id=uuid4(),
        business_id=t["biz_a"],
        name="Branch A1",
        status=BranchStatus.ACTIVE,
    )
    db_session.add(branch)
    await db_session.commit()

    r = await client.get(
        f"/api/v1/businesses/{t['biz_a']}?branch_id={branch.id}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code == 200, r.text


async def test_explicit_scope_denies_other_branch(client, two_tenants, db_session):
    t = two_tenants
    await set_tenant_guc(db_session, None, bypass=True)
    branch_ok = Branch(
        id=uuid4(), business_id=t["biz_a"], name="Allowed", status=BranchStatus.ACTIVE
    )
    branch_bad = Branch(
        id=uuid4(), business_id=t["biz_a"], name="Denied", status=BranchStatus.ACTIVE
    )
    db_session.add_all([branch_ok, branch_bad])
    db_session.add(
        ScopeAssignment(
            id=uuid4(),
            membership_id=t["mem_a"],
            branch_id=branch_ok.id,
            location_id=None,
        )
    )
    await db_session.commit()

    ok = await client.get(
        f"/api/v1/businesses/{t['biz_a']}?branch_id={branch_ok.id}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert ok.status_code == 200, ok.text

    bad = await client.get(
        f"/api/v1/businesses/{t['biz_a']}?branch_id={branch_bad.id}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert bad.status_code == 403, bad.text
    assert "scope" in bad.json()["detail"].lower()


async def test_explicit_scope_allows_business_without_branch_param(
    client, two_tenants, db_session
):
    t = two_tenants
    await set_tenant_guc(db_session, None, bypass=True)
    branch = Branch(
        id=uuid4(), business_id=t["biz_a"], name="Scoped", status=BranchStatus.ACTIVE
    )
    db_session.add(branch)
    db_session.add(
        ScopeAssignment(
            id=uuid4(),
            membership_id=t["mem_a"],
            branch_id=branch.id,
            location_id=None,
        )
    )
    await db_session.commit()

    r = await client.get(
        f"/api/v1/businesses/{t['biz_a']}",
        headers={"Authorization": f"Bearer {t['token_a']}"},
    )
    assert r.status_code == 200, r.text
