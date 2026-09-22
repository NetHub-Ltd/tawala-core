"""T11 CRM — Party-backed profile, notes, purchase history from Sales."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core_platform.crm.service import CrmService
from app.core_platform.sales.service import SalesService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.db.session import set_tenant_guc
from app.models.catalog import CatalogStatus, Product
from app.models.crm import CreditStatus
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
    biz = Business(id=uuid4(), name="CRM Co", status=BusinessStatus.ACTIVE)
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
        name="S1",
        kind=LocationKind.SHOP,
        status=LocationStatus.ACTIVE,
    )
    party = Party(id=uuid4(), kind=PartyKind.PERSON, display_name="Jane Customer")
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="Item",
        sku="I1",
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
    return biz, party, product, loc


@pytest.mark.asyncio
async def test_profile_credit_notes(db_session):
    biz, party, _, _ = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    crm = CrmService(db_session)
    p = await crm.get_or_create_profile(business_id=biz.id, party_id=party.id)
    assert p.credit_status == CreditStatus.NONE
    p = await crm.update_profile(
        business_id=biz.id,
        party_id=party.id,
        credit_status=CreditStatus.GOOD,
        credit_limit=Decimal("1000"),
        segment="retail",
    )
    assert p.credit_status == CreditStatus.GOOD
    assert p.credit_limit == Decimal("1000")
    await crm.add_note(business_id=biz.id, party_id=party.id, body="VIP walk-in")
    notes = await crm.list_notes(biz.id, party.id)
    assert len(notes) == 1
    acts = await crm.list_activity(biz.id, party.id)
    assert any(a.activity_type == "credit_updated" for a in acts)


@pytest.mark.asyncio
async def test_purchase_history_from_sales(db_session):
    biz, party, product, loc = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    # stock for finalize
    from app.core_platform.inventory.service import InventoryService

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
        lines=[
            {
                "product_id": product.id,
                "description": "Item",
                "quantity": Decimal("2"),
                "unit_price": Decimal("25"),
            }
        ],
    )
    await sales.finalize_invoice(business_id=biz.id, invoice_id=inv.id)
    hist = await CrmService(db_session).purchase_history(biz.id, party.id)
    assert len(hist) == 1
    assert hist[0]["total"] == "50.0000" or Decimal(hist[0]["total"]) == Decimal("50")


@pytest.mark.asyncio
async def test_cross_tenant_party_blocked(db_session):
    biz, party, _, _ = await _seed(db_session)
    other = Business(id=uuid4(), name="Other", status=BusinessStatus.ACTIVE)
    db_session.add(other)
    await db_session.commit()
    await set_tenant_guc(db_session, None, bypass=True)
    with pytest.raises(DomainError) as ei:
        await CrmService(db_session).get_or_create_profile(
            business_id=other.id, party_id=party.id
        )
    assert ei.value.code == DomainErrorCode.NOT_FOUND
