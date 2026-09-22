"""Duplicate idempotency keys must not double-apply money/stock effects (#294)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.inventory.service import InventoryService
from app.db.session import set_tenant_guc
from app.models.catalog import CatalogStatus, Product
from app.models.inventory import StockLevel
from app.models.organization import (
    Branch,
    BranchStatus,
    Business,
    BusinessStatus,
    Location,
    LocationKind,
    LocationStatus,
)


async def _seed(session: AsyncSession) -> dict:
    await set_tenant_guc(session, None, bypass=True)
    biz = Business(id=uuid4(), name="Idem Biz", status=BusinessStatus.ACTIVE)
    session.add(biz)
    await session.flush()
    branch = Branch(
        id=uuid4(), business_id=biz.id, name="B1", status=BranchStatus.ACTIVE
    )
    session.add(branch)
    await session.flush()
    loc = Location(
        id=uuid4(),
        business_id=biz.id,
        branch_id=branch.id,
        name="Shop",
        kind=LocationKind.SHOP,
        status=LocationStatus.ACTIVE,
    )
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Idem SKU",
        sku=f"ID-{uuid4().hex[:6]}",
        status=CatalogStatus.ACTIVE,
    )
    session.add_all([loc, product])
    await session.commit()
    await set_tenant_guc(session, None, bypass=True)
    return {"biz": biz.id, "loc": loc.id, "product": product.id}


@pytest.mark.asyncio
async def test_inventory_receive_duplicate_key_no_double_qty(db_session):
    t = await _seed(db_session)
    inv = InventoryService(db_session)
    key = f"recv-{uuid4()}"
    await inv.receive(
        business_id=t["biz"],
        product_id=t["product"],
        location_id=t["loc"],
        quantity=Decimal("10"),
        idempotency_key=key,
    )
    await inv.receive(
        business_id=t["biz"],
        product_id=t["product"],
        location_id=t["loc"],
        quantity=Decimal("10"),
        idempotency_key=key,
    )
    await set_tenant_guc(db_session, None, bypass=True)
    level = (
        await db_session.exec(
            select(StockLevel).where(
                StockLevel.business_id == t["biz"],
                StockLevel.product_id == t["product"],
                StockLevel.location_id == t["loc"],
            )
        )
    ).first()
    assert level is not None
    assert level.quantity_on_hand == Decimal("10")
