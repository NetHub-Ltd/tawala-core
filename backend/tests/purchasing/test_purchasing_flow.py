"""T9 Purchasing — PO → partial/full receive → stock + liability + payment."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.inventory.service import InventoryService
from app.core_platform.purchasing.service import PurchasingService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.db.session import set_tenant_guc
from app.models.accounting import FinancialEntry, FinancialEntryType
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
from app.models.parties import (
    LinkStatus,
    Party,
    PartyBusinessLink,
    PartyKind,
    PartyRelationship,
)
from app.models.purchasing import PurchaseOrderStatus


async def _seed(session):
    await set_tenant_guc(session, None, bypass=True)
    biz = Business(id=uuid4(), name="Buy Co", status=BusinessStatus.ACTIVE)
    session.add(biz)
    await session.flush()
    branch = Branch(
        id=uuid4(), business_id=biz.id, name="HQ", status=BranchStatus.ACTIVE
    )
    session.add(branch)
    await session.flush()
    loc = Location(
        id=uuid4(),
        business_id=biz.id,
        branch_id=branch.id,
        name="WH",
        kind=LocationKind.WAREHOUSE,
        status=LocationStatus.ACTIVE,
    )
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Raw",
        sku="R1",
        status=CatalogStatus.ACTIVE,
    )
    supplier = Party(
        id=uuid4(), kind=PartyKind.ORGANIZATION, display_name="Supplier Ltd"
    )
    session.add_all([loc, product, supplier])
    await session.flush()
    session.add(
        PartyBusinessLink(
            id=uuid4(),
            business_id=biz.id,
            party_id=supplier.id,
            relationship=PartyRelationship.SUPPLIER,
            status=LinkStatus.ACTIVE,
        )
    )
    await session.commit()
    return biz, product, loc, supplier


@pytest.mark.asyncio
async def test_partial_then_full_receive(db_session):
    biz, product, loc, supplier = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = PurchasingService(db_session)

    po = await svc.create_order(
        business_id=biz.id,
        party_id=supplier.id,
        location_id=loc.id,
        lines=[
            {
                "product_id": product.id,
                "description": "Raw",
                "quantity_ordered": Decimal("10"),
                "unit_cost": Decimal("5"),
            }
        ],
    )
    await svc.confirm_order(business_id=biz.id, po_id=po.id)

    from sqlmodel import select
    from app.models.purchasing import PurchaseOrderLine

    lines = (
        await db_session.exec(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
        )
    ).all()
    pol = lines[0]

    grn1 = await svc.create_receipt(
        business_id=biz.id,
        purchase_order_id=po.id,
        location_id=loc.id,
        lines=[{"purchase_order_line_id": pol.id, "quantity": Decimal("4")}],
    )
    await svc.finalize_receipt(business_id=biz.id, receipt_id=grn1.id)

    po = await svc._get_po(biz.id, po.id)
    assert po.status == PurchaseOrderStatus.PARTIALLY_RECEIVED
    level = await InventoryService(db_session).get_level(biz.id, product.id, loc.id)
    assert level.quantity_on_hand == Decimal("4")

    grn2 = await svc.create_receipt(
        business_id=biz.id,
        purchase_order_id=po.id,
        location_id=loc.id,
        lines=[{"purchase_order_line_id": pol.id, "quantity": Decimal("6")}],
    )
    await svc.finalize_receipt(business_id=biz.id, receipt_id=grn2.id)
    po = await svc._get_po(biz.id, po.id)
    assert po.status == PurchaseOrderStatus.RECEIVED
    level = await InventoryService(db_session).get_level(biz.id, product.id, loc.id)
    assert level.quantity_on_hand == Decimal("10")

    entries = (
        await db_session.exec(
            select(FinancialEntry).where(
                FinancialEntry.entry_type == FinancialEntryType.SUPPLIER_LIABILITY,
                FinancialEntry.business_id == biz.id,
            )
        )
    ).all()
    assert sum(e.amount for e in entries) == Decimal("50")  # 10 * 5

    pay = await svc.record_payment(
        business_id=biz.id, purchase_order_id=po.id, amount=Decimal("50")
    )
    assert pay.amount == Decimal("50")


@pytest.mark.asyncio
async def test_over_receive_rejected(db_session):
    biz, product, loc, supplier = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = PurchasingService(db_session)
    po = await svc.create_order(
        business_id=biz.id,
        party_id=supplier.id,
        location_id=loc.id,
        lines=[
            {
                "product_id": product.id,
                "description": "Raw",
                "quantity_ordered": Decimal("3"),
                "unit_cost": Decimal("1"),
            }
        ],
    )
    await svc.confirm_order(business_id=biz.id, po_id=po.id)
    from app.models.purchasing import PurchaseOrderLine

    pol = (
        await db_session.exec(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
        )
    ).first()
    with pytest.raises(DomainError) as ei:
        await svc.create_receipt(
            business_id=biz.id,
            purchase_order_id=po.id,
            location_id=loc.id,
            lines=[{"purchase_order_line_id": pol.id, "quantity": Decimal("9")}],
        )
    assert ei.value.code == DomainErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_cancel_after_receive_rejected(db_session):
    biz, product, loc, supplier = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = PurchasingService(db_session)
    po = await svc.create_order(
        business_id=biz.id,
        party_id=supplier.id,
        lines=[
            {
                "product_id": product.id,
                "description": "Raw",
                "quantity_ordered": Decimal("2"),
                "unit_cost": Decimal("1"),
            }
        ],
    )
    await svc.confirm_order(business_id=biz.id, po_id=po.id)
    from app.models.purchasing import PurchaseOrderLine

    pol = (
        await db_session.exec(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
        )
    ).first()
    grn = await svc.create_receipt(
        business_id=biz.id,
        purchase_order_id=po.id,
        location_id=loc.id,
        lines=[{"purchase_order_line_id": pol.id, "quantity": Decimal("1")}],
    )
    await svc.finalize_receipt(business_id=biz.id, receipt_id=grn.id)
    with pytest.raises(DomainError):
        await svc.cancel_order(business_id=biz.id, po_id=po.id)
