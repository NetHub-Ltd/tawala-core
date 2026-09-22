"""T8 Sales — quote→order→invoice→finalize→pay; stock via Inventory; finance via Accounting."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.inventory.service import InventoryService
from app.core_platform.sales.service import SalesService
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
from app.models.sales import SalesDocumentStatus, SalesDocumentType


async def _seed(session):
    await set_tenant_guc(session, None, bypass=True)
    biz = Business(id=uuid4(), name="Sales Co", status=BusinessStatus.ACTIVE)
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
        name="Floor",
        kind=LocationKind.SHOP,
        status=LocationStatus.ACTIVE,
    )
    product = Product(
        id=uuid4(),
        business_id=biz.id,
        name="SKU1",
        sku="S1",
        status=CatalogStatus.ACTIVE,
    )
    session.add_all([loc, product])
    await session.commit()
    inv = InventoryService(session)
    await inv.receive(
        business_id=biz.id,
        product_id=product.id,
        location_id=loc.id,
        quantity=Decimal("100"),
    )
    return biz, product, loc, branch


@pytest.mark.asyncio
async def test_quote_order_invoice_finalize_payment(db_session):
    biz, product, loc, branch = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    sales = SalesService(db_session)

    quote = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.QUOTE,
        location_id=loc.id,
        branch_id=branch.id,
        lines=[
            {
                "product_id": product.id,
                "description": "SKU1",
                "quantity": Decimal("2"),
                "unit_price": Decimal("50"),
            }
        ],
    )
    assert quote.status == SalesDocumentStatus.DRAFT
    assert quote.document_number.startswith("QUO-")

    order = await sales.convert_quote_to_order(business_id=biz.id, quote_id=quote.id)
    assert order.document_type == SalesDocumentType.ORDER

    invoice = await sales.convert_order_to_invoice(business_id=biz.id, order_id=order.id)
    assert invoice.document_type == SalesDocumentType.INVOICE

    finalized = await sales.finalize_invoice(business_id=biz.id, invoice_id=invoice.id)
    assert finalized.status == SalesDocumentStatus.FINALIZED

    # double finalize rejected
    with pytest.raises(DomainError) as ei:
        await sales.finalize_invoice(business_id=biz.id, invoice_id=invoice.id)
    assert ei.value.code == DomainErrorCode.ALREADY_PROCESSED

    level = await InventoryService(db_session).get_level(biz.id, product.id, loc.id)
    assert level.quantity_on_hand == Decimal("98")

    entries = (
        await db_session.exec(
            select(FinancialEntry).where(
                FinancialEntry.source_id == invoice.id,
                FinancialEntry.entry_type == FinancialEntryType.SALE_REVENUE,
            )
        )
    ).all()
    assert len(entries) == 1
    assert entries[0].amount == Decimal("100")

    pay = await sales.record_payment(
        business_id=biz.id, invoice_id=invoice.id, amount=Decimal("100")
    )
    assert pay.amount == Decimal("100")


@pytest.mark.asyncio
async def test_finalize_idempotent(db_session):
    biz, product, loc, branch = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    sales = SalesService(db_session)
    inv_doc = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.INVOICE,
        location_id=loc.id,
        branch_id=branch.id,
        lines=[
            {
                "product_id": product.id,
                "description": "x",
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    key = f"fin-{uuid4()}"
    a = await sales.finalize_invoice(
        business_id=biz.id, invoice_id=inv_doc.id, idempotency_key=key
    )
    b = await sales.finalize_invoice(
        business_id=biz.id, invoice_id=inv_doc.id, idempotency_key=key
    )
    assert a.id == b.id
    level = await InventoryService(db_session).get_level(biz.id, product.id, loc.id)
    assert level.quantity_on_hand == Decimal("99")


@pytest.mark.asyncio
async def test_return_references_invoice_and_restocks(db_session):
    biz, product, loc, branch = await _seed(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    sales = SalesService(db_session)
    inv_doc = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.INVOICE,
        location_id=loc.id,
        lines=[
            {
                "product_id": product.id,
                "description": "x",
                "quantity": Decimal("5"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    await sales.finalize_invoice(business_id=biz.id, invoice_id=inv_doc.id)

    ret = await sales.create_document(
        business_id=biz.id,
        document_type=SalesDocumentType.RETURN_CREDIT,
        location_id=loc.id,
        source_document_id=inv_doc.id,
        lines=[
            {
                "product_id": product.id,
                "description": "x",
                "quantity": Decimal("2"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    await sales.finalize_return(business_id=biz.id, return_id=ret.id)
    level = await InventoryService(db_session).get_level(biz.id, product.id, loc.id)
    assert level.quantity_on_hand == Decimal("97")  # 100-5+2
