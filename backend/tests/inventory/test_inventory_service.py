"""T7 Inventory — receive/issue/adjust/transfer, negative policy, idempotency."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core_platform.inventory.service import InventoryService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.db.session import set_tenant_guc
from app.models.catalog import CatalogStatus, Product
from app.models.organization import (
    Branch,
    BranchStatus,
    Business,
    BusinessStatus,
    Location,
    LocationKind,
    LocationStatus,
)


async def _seed_biz_product_locations(session):
    await set_tenant_guc(session, None, bypass=True)
    biz = Business(id=uuid4(), name="Inv Co", status=BusinessStatus.ACTIVE)
    session.add(biz)
    await session.flush()
    branch = Branch(
        id=uuid4(),
        business_id=biz.id,
        name="Main",
        status=BranchStatus.ACTIVE,
    )
    session.add(branch)
    await session.flush()
    loc_a = Location(
        id=uuid4(),
        business_id=biz.id,
        branch_id=branch.id,
        name="Warehouse A",
        kind=LocationKind.WAREHOUSE,
        status=LocationStatus.ACTIVE,
    )
    loc_b = Location(
        id=uuid4(),
        business_id=biz.id,
        branch_id=branch.id,
        name="Shop B",
        kind=LocationKind.SHOP,
        status=LocationStatus.ACTIVE,
    )
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Widget",
        sku=f"W-{uuid4().hex[:6]}",
        status=CatalogStatus.ACTIVE,
    )
    session.add_all([loc_a, loc_b, product])
    await session.commit()
    return biz, product, loc_a, loc_b


@pytest.mark.asyncio
async def test_receive_and_issue(db_session):
    biz, product, loc_a, _ = await _seed_biz_product_locations(db_session)
    svc = InventoryService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)

    mov = await svc.receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity=Decimal("10"),
    )
    assert mov.quantity_after == Decimal("10")
    level = await svc.get_level(biz.id, product.id, loc_a.id)
    assert level is not None
    assert level.quantity_on_hand == Decimal("10")

    await svc.issue(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity=Decimal("3"),
    )
    level = await svc.get_level(biz.id, product.id, loc_a.id)
    assert level.quantity_on_hand == Decimal("7")


@pytest.mark.asyncio
async def test_negative_stock_rejected(db_session):
    biz, product, loc_a, _ = await _seed_biz_product_locations(db_session)
    svc = InventoryService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    await svc.receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity=Decimal("2"),
    )
    with pytest.raises(DomainError) as ei:
        await svc.issue(
            business_id=biz.id,
            product_id=product.id,
            location_id=loc_a.id,
            quantity=Decimal("5"),
        )
    assert ei.value.code == DomainErrorCode.VALIDATION_FAILED
    level = await svc.get_level(biz.id, product.id, loc_a.id)
    assert level.quantity_on_hand == Decimal("2")


@pytest.mark.asyncio
async def test_adjust_and_transfer_atomic(db_session):
    biz, product, loc_a, loc_b = await _seed_biz_product_locations(db_session)
    svc = InventoryService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)

    await svc.adjust(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity_on_hand=Decimal("20"),
        reason_code="opening",
    )
    out_m, in_m = await svc.transfer(
        business_id=biz.id,
        product_id=product.id,
        from_location_id=loc_a.id,
        to_location_id=loc_b.id,
        quantity=Decimal("8"),
    )
    assert out_m.transfer_group_id == in_m.transfer_group_id
    assert out_m.quantity_delta == Decimal("-8")
    assert in_m.quantity_delta == Decimal("8")
    a = await svc.get_level(biz.id, product.id, loc_a.id)
    b = await svc.get_level(biz.id, product.id, loc_b.id)
    assert a.quantity_on_hand == Decimal("12")
    assert b.quantity_on_hand == Decimal("8")


@pytest.mark.asyncio
async def test_receive_idempotent(db_session):
    biz, product, loc_a, _ = await _seed_biz_product_locations(db_session)
    svc = InventoryService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    key = f"recv-{uuid4()}"
    m1 = await svc.receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity=Decimal("5"),
        idempotency_key=key,
    )
    m2 = await svc.receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc_a.id,
        quantity=Decimal("5"),
        idempotency_key=key,
    )
    assert m1.id == m2.id
    level = await svc.get_level(biz.id, product.id, loc_a.id)
    assert level.quantity_on_hand == Decimal("5")


@pytest.mark.asyncio
async def test_cross_tenant_product_rejected(db_session):
    biz, product, loc_a, _ = await _seed_biz_product_locations(db_session)
    other = Business(id=uuid4(), name="Other", status=BusinessStatus.ACTIVE)
    db_session.add(other)
    await db_session.commit()
    svc = InventoryService(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    with pytest.raises(DomainError) as ei:
        await svc.receive(
            business_id=other.id,
            product_id=product.id,
            location_id=loc_a.id,
            quantity=Decimal("1"),
        )
    assert ei.value.code == DomainErrorCode.NOT_FOUND
