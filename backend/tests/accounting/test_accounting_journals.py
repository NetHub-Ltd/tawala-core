"""T10 Accounting — balanced journals, reversals, domain adapter, tax hook."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.accounting.service import AccountingService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.db.session import set_tenant_guc
from app.models.accounting import (
    FinancialEntryType,
    JournalEntry,
    JournalLine,
    JournalStatus,
)
from app.models.organization import Business, BusinessStatus


async def _biz(session):
    await set_tenant_guc(session, None, bypass=True)
    b = Business(id=uuid4(), name="Books Co", status=BusinessStatus.ACTIVE)
    session.add(b)
    await session.commit()
    return b


@pytest.mark.asyncio
async def test_sale_posts_balanced_journal(db_session):
    biz = await _biz(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = AccountingService(db_session)
    src = uuid4()
    fe = await svc.post_entry(
        business_id=biz.id,
        entry_type=FinancialEntryType.SALE_REVENUE,
        amount=Decimal("100"),
        source_type="sales_document",
        source_id=src,
        tax_amount=Decimal("16"),
        tax_code="VAT16",
        commit=True,
    )
    assert fe.journal_entry_id is not None
    lines = list(
        (
            await db_session.exec(
                select(JournalLine).where(
                    JournalLine.journal_entry_id == fe.journal_entry_id
                )
            )
        ).all()
    )
    debits = sum(ln.debit for ln in lines)
    credits = sum(ln.credit for ln in lines)
    assert debits == credits == Decimal("116")


@pytest.mark.asyncio
async def test_unbalanced_rejected(db_session):
    biz = await _biz(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = AccountingService(db_session)
    coa = await svc.ensure_chart_of_accounts(biz.id)
    with pytest.raises(DomainError) as ei:
        await svc.post_journal(
            business_id=biz.id,
            source_type="test",
            source_id=uuid4(),
            lines=[
                {"account_id": coa["1000"].id, "debit": Decimal("10"), "credit": Decimal("0")},
                {"account_id": coa["4000"].id, "debit": Decimal("0"), "credit": Decimal("5")},
            ],
            commit=True,
        )
    assert ei.value.code == DomainErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_reversal_preserves_history(db_session):
    biz = await _biz(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = AccountingService(db_session)
    fe = await svc.post_entry(
        business_id=biz.id,
        entry_type=FinancialEntryType.SUPPLIER_LIABILITY,
        amount=Decimal("50"),
        source_type="goods_receipt",
        source_id=uuid4(),
        commit=True,
    )
    rev = await svc.reverse_journal(
        business_id=biz.id, journal_entry_id=fe.journal_entry_id, commit=True
    )
    orig = await db_session.get(JournalEntry, fe.journal_entry_id)
    assert orig.status == JournalStatus.REVERSED
    assert orig.reversed_by_entry_id == rev.id
    assert rev.reverses_entry_id == orig.id
    assert rev.status == JournalStatus.POSTED


@pytest.mark.asyncio
async def test_payment_allocates(db_session):
    biz = await _biz(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = AccountingService(db_session)
    invoice_id = uuid4()
    fe = await svc.post_entry(
        business_id=biz.id,
        entry_type=FinancialEntryType.CUSTOMER_RECEIPT,
        amount=Decimal("40"),
        source_type="sales_document",
        source_id=invoice_id,
        commit=True,
    )
    from app.models.accounting import PaymentAllocation

    allocs = list(
        (
            await db_session.exec(
                select(PaymentAllocation).where(
                    PaymentAllocation.payment_journal_id == fe.journal_entry_id
                )
            )
        ).all()
    )
    assert len(allocs) == 1
    assert allocs[0].target_source_id == invoice_id
    assert allocs[0].amount == Decimal("40")


@pytest.mark.asyncio
async def test_duplicate_post_idempotent(db_session):
    biz = await _biz(db_session)
    await set_tenant_guc(db_session, None, bypass=True)
    svc = AccountingService(db_session)
    key = f"acct-{uuid4()}"
    src = uuid4()
    a = await svc.post_entry(
        business_id=biz.id,
        entry_type=FinancialEntryType.SALE_REVENUE,
        amount=Decimal("10"),
        source_type="sales_document",
        source_id=src,
        idempotency_key=key,
        commit=True,
    )
    b = await svc.post_entry(
        business_id=biz.id,
        entry_type=FinancialEntryType.SALE_REVENUE,
        amount=Decimal("10"),
        source_type="sales_document",
        source_id=src,
        idempotency_key=key,
        commit=True,
    )
    assert a.id == b.id
