"""T5 entitlement kernel — grant, require, deny-by-default."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.entitlements import BusinessEntitlement, Capability
from app.models.organization import Business, BusinessStatus


@pytest.mark.asyncio
async def test_seed_and_grant_require(db_session):
    svc = EntitlementService(db_session)
    n = await svc.ensure_catalog_seeded()
    assert n >= 1
    # idempotent
    assert await svc.ensure_catalog_seeded() == 0

    biz = Business(id=uuid4(), name="Entitled Co", status=BusinessStatus.ACTIVE)
    db_session.add(biz)
    await db_session.commit()

    assert await svc.has(biz.id, "module.catalog") is False
    with pytest.raises(DomainError) as ei:
        await svc.require(biz.id, "module.catalog")
    assert ei.value.code == DomainErrorCode.FORBIDDEN

    row = await svc.grant(biz.id, "module.catalog", source="test")
    assert row.capability_code == "module.catalog"
    assert await svc.has(biz.id, "module.catalog") is True
    await svc.require(biz.id, "module.catalog")  # no raise


@pytest.mark.asyncio
async def test_limit_requires_value(db_session):
    svc = EntitlementService(db_session)
    await svc.ensure_catalog_seeded()
    biz = Business(id=uuid4(), name="Limit Co", status=BusinessStatus.ACTIVE)
    db_session.add(biz)
    await db_session.commit()

    with pytest.raises(DomainError) as ei:
        await svc.grant(biz.id, "limit.staff.max")
    assert ei.value.code == DomainErrorCode.VALIDATION_FAILED

    row = await svc.grant(biz.id, "limit.staff.max", limit_value=5, source="plan")
    assert row.limit_value == 5
    assert await svc.limit(biz.id, "limit.staff.max") == 5


@pytest.mark.asyncio
async def test_revoke(db_session):
    svc = EntitlementService(db_session)
    await svc.ensure_catalog_seeded()
    biz = Business(id=uuid4(), name="Revoke Co", status=BusinessStatus.ACTIVE)
    db_session.add(biz)
    await db_session.commit()
    await svc.grant(biz.id, "module.sales", source="test")
    await svc.revoke(biz.id, "module.sales")
    assert await svc.has(biz.id, "module.sales") is False
