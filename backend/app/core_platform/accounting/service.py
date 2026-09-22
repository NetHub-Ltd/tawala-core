"""AccountingService — authoritative financial truth (T10).

post_entry remains the adapter used by Sales/Purchasing. It posts a balanced
journal (source of truth) and a legacy FinancialEntry row linked to that journal.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared import idempotency as idem
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.accounting import (
    Account,
    AccountType,
    FinancialEntry,
    FinancialEntryType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    PaymentAllocation,
)
from app.models.base import utc_now

# System COA codes
CASH = "1000"
AR = "1100"
AP = "2000"
TAX_PAYABLE = "2100"
REVENUE = "4000"
INVENTORY_EXPENSE = "5000"  # purchase / COGS placeholder
SALES_RETURNS = "4100"

_SYSTEM_COA: list[tuple[str, str, AccountType]] = [
    (CASH, "Cash", AccountType.ASSET),
    (AR, "Accounts Receivable", AccountType.ASSET),
    (AP, "Accounts Payable", AccountType.LIABILITY),
    (TAX_PAYABLE, "Tax Payable", AccountType.LIABILITY),
    (REVENUE, "Sales Revenue", AccountType.REVENUE),
    (SALES_RETURNS, "Sales Returns", AccountType.REVENUE),
    (INVENTORY_EXPENSE, "Purchases / Inventory", AccountType.EXPENSE),
]


class AccountingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_chart_of_accounts(self, business_id: UUID) -> dict[str, Account]:
        by_code: dict[str, Account] = {}
        for code, name, atype in _SYSTEM_COA:
            row = (
                await self._session.exec(
                    select(Account).where(
                        Account.business_id == business_id,
                        Account.code == code,
                        Account.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).first()
            if row is None:
                row = Account(
                    id=uuid4(),
                    business_id=business_id,
                    code=code,
                    name=name,
                    account_type=atype,
                    is_system=True,
                )
                self._session.add(row)
                await self._session.flush()
            by_code[code] = row
        return by_code

    async def _next_journal_number(self, business_id: UUID) -> str:
        n = len(
            (
                await self._session.exec(
                    select(JournalEntry).where(JournalEntry.business_id == business_id)
                )
            ).all()
        )
        return f"JE-{n + 1:06d}"

    def _assert_balanced(self, lines: list[tuple[UUID, Decimal, Decimal]]) -> None:
        debits = sum((d for _, d, _ in lines), Decimal("0"))
        credits = sum((c for _, _, c in lines), Decimal("0"))
        if debits != credits:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED,
                f"Unbalanced journal: debits={debits} credits={credits}",
            )
        if debits <= 0:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, "Journal must have non-zero amount"
            )

    async def post_journal(
        self,
        *,
        business_id: UUID,
        source_type: str,
        source_id: UUID,
        lines: list[dict],
        currency: str = "KES",
        party_id: UUID | None = None,
        memo: str | None = None,
        domain_entry_type: str | None = None,
        reverses_entry_id: UUID | None = None,
        commit: bool = False,
        idempotency_key: str | None = None,
    ) -> JournalEntry:
        """Post a balanced journal. lines: {account_id, debit, credit, tax_code?, tax_amount?}."""
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                existing = await self._session.get(JournalEntry, prior.resource_id)
                if existing is not None:
                    return existing
        if not lines:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "Journal requires lines")

        parsed: list[tuple[UUID, Decimal, Decimal]] = []
        for raw in lines:
            debit = Decimal(str(raw.get("debit") or 0))
            credit = Decimal(str(raw.get("credit") or 0))
            if debit < 0 or credit < 0:
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED, "Debit/credit cannot be negative"
                )
            if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED,
                    "Each line must have either debit or credit (not both, not neither)",
                )
            parsed.append((raw["account_id"], debit, credit))
        self._assert_balanced(parsed)

        entry = JournalEntry(
            id=uuid4(),
            business_id=business_id,
            entry_number=await self._next_journal_number(business_id),
            status=JournalStatus.POSTED,
            source_type=source_type,
            source_id=source_id,
            domain_entry_type=domain_entry_type,
            currency=currency,
            memo=memo,
            party_id=party_id,
            occurred_at=utc_now(),
            posted_at=utc_now(),
            reverses_entry_id=reverses_entry_id,
        )
        self._session.add(entry)
        await self._session.flush()
        for raw in lines:
            self._session.add(
                JournalLine(
                    id=uuid4(),
                    business_id=business_id,
                    journal_entry_id=entry.id,
                    account_id=raw["account_id"],
                    debit=Decimal(str(raw.get("debit") or 0)),
                    credit=Decimal(str(raw.get("credit") or 0)),
                    party_id=raw.get("party_id") or party_id,
                    tax_code=raw.get("tax_code"),
                    tax_amount=Decimal(str(raw.get("tax_amount") or 0)),
                    memo=raw.get("memo"),
                )
            )
        if reverses_entry_id:
            orig = await self._session.get(JournalEntry, reverses_entry_id)
            if orig is not None:
                orig.status = JournalStatus.REVERSED
                orig.reversed_by_entry_id = entry.id
                orig.touch()
                self._session.add(orig)

        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="accounting.journal.post",
            event_type="accounting.journal.posted",
            resource_type="journal_entry",
            resource_id=entry.id,
            business_id=business_id,
            actor_user_id=None,
            payload={"number": entry.entry_number, "source_type": source_type},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="accounting.journal.post",
                response_body={"id": str(entry.id), "number": entry.entry_number},
                response_status=201,
                resource_id=entry.id,
                commit=False,
            )
        if commit:
            await self._session.commit()
            await self._session.refresh(entry)
        else:
            await self._session.flush()
        return entry

    async def reverse_journal(
        self,
        *,
        business_id: UUID,
        journal_entry_id: UUID,
        memo: str | None = None,
        commit: bool = False,
    ) -> JournalEntry:
        """Create compensating journal; original marked reversed (history preserved)."""
        orig = await self._session.get(JournalEntry, journal_entry_id)
        if orig is None or orig.business_id != business_id or orig.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Journal entry not found")
        if orig.status == JournalStatus.REVERSED:
            raise DomainError(DomainErrorCode.ALREADY_PROCESSED, "Journal already reversed")
        if orig.status != JournalStatus.POSTED:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, "Only posted journals can be reversed"
            )
        lines = list(
            (
                await self._session.exec(
                    select(JournalLine).where(
                        JournalLine.journal_entry_id == orig.id,
                        JournalLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        rev_lines = [
            {
                "account_id": ln.account_id,
                "debit": ln.credit,
                "credit": ln.debit,
                "party_id": ln.party_id,
                "tax_code": ln.tax_code,
                "tax_amount": ln.tax_amount,
                "memo": f"Reversal of {orig.entry_number}",
            }
            for ln in lines
        ]
        return await self.post_journal(
            business_id=business_id,
            source_type=orig.source_type,
            source_id=orig.source_id,
            lines=rev_lines,
            currency=orig.currency,
            party_id=orig.party_id,
            memo=memo or f"Reversal of {orig.entry_number}",
            domain_entry_type=orig.domain_entry_type,
            reverses_entry_id=orig.id,
            commit=commit,
        )

    async def allocate_payment(
        self,
        *,
        business_id: UUID,
        payment_journal_id: UUID,
        target_source_type: str,
        target_source_id: UUID,
        amount: Decimal,
        currency: str = "KES",
        commit: bool = False,
    ) -> PaymentAllocation:
        amt = Decimal(amount)
        if amt <= 0:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "allocation amount must be positive")
        je = await self._session.get(JournalEntry, payment_journal_id)
        if je is None or je.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Payment journal not found")
        row = PaymentAllocation(
            id=uuid4(),
            business_id=business_id,
            payment_journal_id=payment_journal_id,
            target_source_type=target_source_type,
            target_source_id=target_source_id,
            amount=amt,
            currency=currency,
        )
        self._session.add(row)
        if commit:
            await self._session.commit()
            await self._session.refresh(row)
        else:
            await self._session.flush()
        return row

    async def post_entry(
        self,
        *,
        business_id: UUID,
        entry_type: FinancialEntryType,
        amount: Decimal,
        source_type: str,
        source_id: UUID,
        currency: str = "KES",
        party_id: UUID | None = None,
        memo: str | None = None,
        tax_code: str | None = None,
        tax_amount: Decimal | None = None,
        commit: bool = False,
        idempotency_key: str | None = None,
    ) -> FinancialEntry:
        """Domain adapter: map Sales/Purchasing events to balanced journals.

        Tax hook: optional tax_amount posts to Tax Payable with revenue/expense netted.
        """
        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(self._session, scope=str(business_id), key=key)
            if prior and prior.resource_id:
                existing = await self._session.get(FinancialEntry, prior.resource_id)
                if existing is not None:
                    return existing

        amt = Decimal(amount)
        if amt <= 0:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "amount must be positive")
        tax = Decimal(tax_amount or 0)
        if tax < 0:
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "tax_amount cannot be negative")

        coa = await self.ensure_chart_of_accounts(business_id)

        # Build balanced lines from domain entry type (AR/AP primitives)
        if entry_type == FinancialEntryType.SALE_REVENUE:
            # DR AR (amt+tax), CR Revenue (amt), CR Tax payable (tax)
            net = amt
            gross = amt + tax
            lines = [
                {"account_id": coa[AR].id, "debit": gross, "credit": Decimal("0")},
                {"account_id": coa[REVENUE].id, "debit": Decimal("0"), "credit": net},
            ]
            if tax > 0:
                lines.append(
                    {
                        "account_id": coa[TAX_PAYABLE].id,
                        "debit": Decimal("0"),
                        "credit": tax,
                        "tax_code": tax_code,
                        "tax_amount": tax,
                    }
                )
        elif entry_type == FinancialEntryType.CUSTOMER_RECEIPT:
            lines = [
                {"account_id": coa[CASH].id, "debit": amt, "credit": Decimal("0")},
                {"account_id": coa[AR].id, "debit": Decimal("0"), "credit": amt},
            ]
        elif entry_type == FinancialEntryType.SALE_RETURN:
            net = amt
            gross = amt + tax
            lines = [
                {"account_id": coa[SALES_RETURNS].id, "debit": net, "credit": Decimal("0")},
                {"account_id": coa[AR].id, "debit": Decimal("0"), "credit": gross},
            ]
            if tax > 0:
                lines.append(
                    {
                        "account_id": coa[TAX_PAYABLE].id,
                        "debit": tax,
                        "credit": Decimal("0"),
                        "tax_code": tax_code,
                        "tax_amount": tax,
                    }
                )
        elif entry_type == FinancialEntryType.SUPPLIER_LIABILITY:
            lines = [
                {
                    "account_id": coa[INVENTORY_EXPENSE].id,
                    "debit": amt,
                    "credit": Decimal("0"),
                },
                {"account_id": coa[AP].id, "debit": Decimal("0"), "credit": amt},
            ]
        elif entry_type == FinancialEntryType.SUPPLIER_PAYMENT:
            lines = [
                {"account_id": coa[AP].id, "debit": amt, "credit": Decimal("0")},
                {"account_id": coa[CASH].id, "debit": Decimal("0"), "credit": amt},
            ]
        else:
            raise DomainError(
                DomainErrorCode.VALIDATION_FAILED, f"Unknown entry_type {entry_type}"
            )

        journal = await self.post_journal(
            business_id=business_id,
            source_type=source_type,
            source_id=source_id,
            lines=lines,
            currency=currency,
            party_id=party_id,
            memo=memo,
            domain_entry_type=entry_type.value,
            commit=False,
        )

        if entry_type in (
            FinancialEntryType.CUSTOMER_RECEIPT,
            FinancialEntryType.SUPPLIER_PAYMENT,
        ):
            await self.allocate_payment(
                business_id=business_id,
                payment_journal_id=journal.id,
                target_source_type=source_type,
                target_source_id=source_id,
                amount=amt,
                currency=currency,
                commit=False,
            )

        row = FinancialEntry(
            id=uuid4(),
            business_id=business_id,
            entry_type=entry_type,
            amount=amt,
            currency=currency,
            source_type=source_type,
            source_id=source_id,
            party_id=party_id,
            memo=memo,
            occurred_at=utc_now(),
            journal_entry_id=journal.id,
        )
        self._session.add(row)
        await self._session.flush()

        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation=f"accounting.post.{entry_type.value}",
                response_body={"id": str(row.id), "journal_id": str(journal.id)},
                response_status=201,
                resource_id=row.id,
                commit=False,
            )
        if commit:
            await self._session.commit()
            await self._session.refresh(row)
        return row
