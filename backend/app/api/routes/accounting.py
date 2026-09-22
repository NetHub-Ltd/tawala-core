"""Accounting read routes (T10)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.models.accounting import Account, JournalEntry

router = APIRouter(prefix="/api/v1", tags=["accounting"])


@router.get("/accounting/accounts")
async def list_accounts(
    ctx: TenantContext = Depends(require_perms("accounting.read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    try:
        await EntitlementService(session).require(ctx.business_id, "module.accounting")
    except DomainError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    rows = list(
        (
            await session.exec(
                select(Account).where(
                    Account.business_id == ctx.business_id,
                    Account.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).all()
    )
    return [
        {"id": str(r.id), "code": r.code, "name": r.name, "account_type": r.account_type}
        for r in rows
    ]


@router.get("/accounting/journals")
async def list_journals(
    source_id: UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_perms("accounting.read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    try:
        await EntitlementService(session).require(ctx.business_id, "module.accounting")
    except DomainError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    stmt = select(JournalEntry).where(
        JournalEntry.business_id == ctx.business_id,
        JournalEntry.deleted_at.is_(None),  # type: ignore[attr-defined]
    )
    if source_id is not None:
        stmt = stmt.where(JournalEntry.source_id == source_id)
    rows = list((await session.exec(stmt)).all())
    return [
        {
            "id": str(r.id),
            "entry_number": r.entry_number,
            "status": r.status,
            "source_type": r.source_type,
            "source_id": str(r.source_id),
            "memo": r.memo,
        }
        for r in rows
    ]
