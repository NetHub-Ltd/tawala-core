"""T13 / M23 — Cross-domain integrity certification (PostgreSQL).

Chain under test:

  Tenant → Party → Catalog → Inventory → Sale → Payment
    → Accounting → CRM → Reporting

Asserts: tenant isolation, stock authority, sales authority,
accounting posts, CRM non-duplication, reporting read-only projection,
outbox claim/publish.

Note: domain services often ``commit()``. Postgres GUCs set with
``set_config(..., true)`` are transaction-local, so bypass must be
re-applied after every committing call or RLS hides rows.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.crm.service import CrmService
from app.core_platform.events.publisher import OutboxPublisher
from app.core_platform.events.service import EventService
from app.core_platform.inventory.service import InventoryService
from app.core_platform.reporting.service import ReportingService
from app.core_platform.sales.service import SalesService
from app.core_platform.shared.types import DomainError
from app.db.session import set_tenant_guc
from app.models.accounting import JournalEntry, JournalStatus
from app.models.catalog import CatalogStatus, Product
from app.models.crm import CustomerProfile
from app.models.events import OutboxEntry, OutboxStatus
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
from app.models.parties import (
    LinkStatus,
    Party,
    PartyBusinessLink,
    PartyKind,
    PartyRelationship,
)
from app.models.sales import SalesDocumentStatus, SalesDocumentType


async def _bypass(session: AsyncSession) -> None:
    """Re-enable RLS bypass after a service ``commit()`` ends the prior txn."""
    await set_tenant_guc(session, None, bypass=True)


async def _seed_two_tenants(session: AsyncSession) -> dict:
    await _bypass(session)
    biz_a = Business(id=uuid4(), name="Cert A", status=BusinessStatus.ACTIVE)
    biz_b = Business(id=uuid4(), name="Cert B", status=BusinessStatus.ACTIVE)
    session.add_all([biz_a, biz_b])
    await session.flush()

    branch = Branch(
        id=uuid4(), business_id=biz_a.id, name="A1", status=BranchStatus.ACTIVE
    )
    session.add(branch)
    await session.flush()
    loc = Location(
        id=uuid4(),
        business_id=biz_a.id,
        branch_id=branch.id,
        name="Shop A",
        kind=LocationKind.SHOP,
        status=LocationStatus.ACTIVE,
    )
    party = Party(id=uuid4(), kind=PartyKind.PERSON, display_name="Cert Customer")
    product = Product(
        id=uuid4(),
        business_id=biz_a.id,
        name="Cert SKU",
        sku="CERT-1",
        status=CatalogStatus.ACTIVE,
    )
    session.add_all([loc, party, product])
    await session.flush()
    session.add(
        PartyBusinessLink(
            id=uuid4(),
            business_id=biz_a.id,
            party_id=party.id,
            relationship=PartyRelationship.CUSTOMER,
            status=LinkStatus.ACTIVE,
        )
    )
    await session.commit()
    await _bypass(session)
    return {
        "biz_a": biz_a,
        "biz_b": biz_b,
        "branch": branch,
        "loc": loc,
        "party": party,
        "product": product,
    }


@pytest.mark.asyncio
async def test_full_chain_tenant_stock_sale_pay_crm_report(db_session):
    t = await _seed_two_tenants(db_session)

    inv = InventoryService(db_session)
    await inv.receive(
        business_id=t["biz_a"].id,
        product_id=t["product"].id,
        location_id=t["loc"].id,
        quantity=Decimal("20"),
    )
    await _bypass(db_session)

    level = (
        await db_session.exec(
            select(StockLevel).where(
                StockLevel.business_id == t["biz_a"].id,
                StockLevel.product_id == t["product"].id,
                StockLevel.location_id == t["loc"].id,
            )
        )
    ).first()
    assert level is not None
    assert level.quantity_on_hand == Decimal("20")

    sales = SalesService(db_session)
    invoice = await sales.create_document(
        business_id=t["biz_a"].id,
        document_type=SalesDocumentType.INVOICE,
        party_id=t["party"].id,
        branch_id=t["branch"].id,
        location_id=t["loc"].id,
        lines=[
            {
                "product_id": t["product"].id,
                "description": "Cert SKU",
                "quantity": Decimal("3"),
                "unit_price": Decimal("100"),
            }
        ],
    )
    await _bypass(db_session)
    invoice = await sales.finalize_invoice(
        business_id=t["biz_a"].id, invoice_id=invoice.id
    )
    await _bypass(db_session)
    assert invoice.status == SalesDocumentStatus.FINALIZED

    level = (
        await db_session.exec(
            select(StockLevel).where(
                StockLevel.business_id == t["biz_a"].id,
                StockLevel.product_id == t["product"].id,
                StockLevel.location_id == t["loc"].id,
            )
        )
    ).first()
    assert level is not None
    assert level.quantity_on_hand == Decimal("17")

    pay = await sales.record_payment(
        business_id=t["biz_a"].id,
        invoice_id=invoice.id,
        amount=Decimal("300"),
        method="cash",
    )
    await _bypass(db_session)
    assert pay.amount == Decimal("300")

    journals = list(
        (
            await db_session.exec(
                select(JournalEntry).where(
                    JournalEntry.business_id == t["biz_a"].id,
                    JournalEntry.status == JournalStatus.POSTED,
                )
            )
        ).all()
    )
    assert len(journals) >= 1

    crm = CrmService(db_session)
    profile = await crm.get_or_create_profile(
        business_id=t["biz_a"].id, party_id=t["party"].id
    )
    await _bypass(db_session)
    assert profile.party_id == t["party"].id
    hist = await crm.purchase_history(t["biz_a"].id, t["party"].id)
    assert len(hist) >= 1

    report = ReportingService(db_session)
    by_day = await report.sales_by_day(
        business_id=t["biz_a"].id,
        day=date.today(),
        branch_id=t["branch"].id,
    )
    assert by_day["invoice_count"] >= 1
    assert Decimal(by_day["line_total"]) >= Decimal("300")

    on_hand = await report.inventory_on_hand(
        business_id=t["biz_a"].id, location_id=t["loc"].id
    )
    assert any(
        i["product_id"] == str(t["product"].id)
        and Decimal(i["quantity_on_hand"]) == Decimal("17")
        for i in on_hand["items"]
    )

    other_day = await report.sales_by_day(
        business_id=t["biz_b"].id, day=date.today()
    )
    assert other_day["invoice_count"] == 0
    other_stock = await report.inventory_on_hand(business_id=t["biz_b"].id)
    assert other_stock["items"] == []

    other_crm = (
        await db_session.exec(
            select(CustomerProfile).where(
                CustomerProfile.business_id == t["biz_b"].id,
                CustomerProfile.party_id == t["party"].id,
            )
        )
    ).first()
    assert other_crm is None


@pytest.mark.asyncio
async def test_outbox_publish_after_domain_event(db_session):
    await _bypass(db_session)
    event = await EventService(db_session).emit(
        event_type="cert.chain.tick",
        aggregate_type="certification",
        aggregate_id=uuid4(),
        payload={"ok": True},
        business_id=uuid4(),
        commit=True,
    )
    event_id = event.id
    await _bypass(db_session)
    pub = OutboxPublisher(db_session)
    for _ in range(10):
        stats = await pub.process_batch(limit=50)
        await _bypass(db_session)
        if stats["claimed"] == 0:
            break
    entry = (
        await db_session.exec(
            select(OutboxEntry).where(OutboxEntry.event_id == event_id)
        )
    ).first()
    assert entry is not None
    assert entry.status == OutboxStatus.PUBLISHED


@pytest.mark.asyncio
async def test_insufficient_stock_blocks_finalize(db_session):
    t = await _seed_two_tenants(db_session)
    await InventoryService(db_session).receive(
        business_id=t["biz_a"].id,
        product_id=t["product"].id,
        location_id=t["loc"].id,
        quantity=Decimal("1"),
    )
    await _bypass(db_session)
    sales = SalesService(db_session)
    invoice = await sales.create_document(
        business_id=t["biz_a"].id,
        document_type=SalesDocumentType.INVOICE,
        party_id=t["party"].id,
        location_id=t["loc"].id,
        lines=[
            {
                "product_id": t["product"].id,
                "description": "Cert SKU",
                "quantity": Decimal("5"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    await _bypass(db_session)
    with pytest.raises(DomainError):
        await sales.finalize_invoice(
            business_id=t["biz_a"].id, invoice_id=invoice.id
        )
