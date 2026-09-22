"""T12 Reporting — read-only projections; tenant-scoped; no mutations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core_platform.inventory.service import InventoryService
from app.core_platform.reporting.service import ReportingService
from app.core_platform.sales.service import SalesService
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
from app.models.parties import (
    LinkStatus,
    Party,
    PartyBusinessLink,
    PartyKind,
    PartyRelationship,
)
from app.models.sales import SalesDocumentType


async def _seed(session):
    await set_tenant_guc(session, None, bypass=True)
    biz = Business(id=uuid4(), name="Report Co", status=BusinessStatus.ACTIVE)
    other = Business(id=uuid4(), name="Other Co", status=BusinessStatus.ACTIVE)
    session.add_all([biz, other])
    await session.flush()
    branch = Branch(
        id=uuid4(), business_id=biz.id, name="Main", status=BranchStatus.ACTIVE
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
    party = Party(id=uuid4(), kind=PartyKind.PERSON, display_name="Cust")
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Widget",
        sku="W1",
        status=CatalogStatus.ACTIVE,
    )
    session.add_all([loc, party, product])
    await session.flush()
    session.add(
        PartyBusinessLink(
            id=uuid4(),
            business_id=biz.id,
            party_id=party.id,
            relationship=PartyRelationship.CUSTOMER,
            status=LinkStatus.ACTIVE,
        )
    )
    await session.commit()
    return biz, other, branch, loc, party, product


@pytest.mark.asyncio
async def test_sales_by_day_from_finalized_invoices(db_session):
    biz, _other, branch, loc, party, product = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    await InventoryService(db_session).receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc.id,
        quantity=Decimal("10"),
    )
    sales = SalesService(db_session)
    inv = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.INVOICE,
        party_id=party.id,
        location_id=loc.id,
        branch_id=branch.id,
        lines=[
            {
                "product_id": product.id,
                "description": "Widget",
                "quantity": Decimal("2"),
                "unit_price": Decimal("50"),
            }
        ],
    )
    await sales.finalize_invoice(business_id=biz.id, invoice_id=inv.id)

    report = ReportingService(db_session)
    today = date.today()
    by_day = await report.sales_by_day(
        business_id=biz.id, day=today, branch_id=branch.id
    )
    assert by_day["invoice_count"] == 1
    assert Decimal(by_day["line_total"]) == Decimal("100")
    assert by_day["source"] == "sales_documents + sales_lines"

    by_prod = await report.sales_by_product(business_id=biz.id, day=today)
    assert len(by_prod["items"]) >= 1

    inv_on = await report.inventory_on_hand(business_id=biz.id, location_id=loc.id)
    assert any(
        i["product_id"] == str(product.id) and Decimal(i["quantity_on_hand"]) == Decimal("8")
        for i in inv_on["items"]
    )


@pytest.mark.asyncio
async def test_tenant_isolation_empty_for_other_business(db_session):
    biz, other, branch, loc, party, product = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    await InventoryService(db_session).receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc.id,
        quantity=Decimal("5"),
    )
    sales = SalesService(db_session)
    inv = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.INVOICE,
        party_id=party.id,
        location_id=loc.id,
        lines=[
            {
                "product_id": product.id,
                "description": "W",
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    await sales.finalize_invoice(business_id=biz.id, invoice_id=inv.id)

    report = ReportingService(db_session)
    other_day = await report.sales_by_day(business_id=other.id, day=date.today())
    assert other_day["invoice_count"] == 0
    other_inv = await report.inventory_on_hand(business_id=other.id)
    assert other_inv["items"] == []


@pytest.mark.asyncio
async def test_reporting_service_has_no_write_api():
    """Guard: ReportingService only exposes async read methods."""
    writes = [
        n
        for n in dir(ReportingService)
        if n.startswith(("create", "update", "delete", "post", "finalize", "emit"))
    ]
    assert writes == []
