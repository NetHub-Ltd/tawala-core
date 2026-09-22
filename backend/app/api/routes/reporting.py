"""Reporting routes (T12) — read-only; no mutations."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.reporting.service import ReportingService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/reporting", tags=["reporting"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def _mod(session: AsyncSession, business_id: UUID) -> None:
    await EntitlementService(session).require(business_id, "module.reporting")


@router.get("/sales/by-day")
async def sales_by_day(
    day: date = Query(...),
    branch_id: UUID | None = None,
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).sales_by_day(
            business_id=ctx.business_id, day=day, branch_id=branch_id
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/sales/by-product")
async def sales_by_product(
    day: date | None = None,
    branch_id: UUID | None = None,
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).sales_by_product(
            business_id=ctx.business_id, day=day, branch_id=branch_id
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/sales/by-customer")
async def sales_by_customer(
    day: date | None = None,
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).sales_by_customer(
            business_id=ctx.business_id, day=day
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/inventory/on-hand")
async def inventory_on_hand(
    location_id: UUID | None = None,
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).inventory_on_hand(
            business_id=ctx.business_id, location_id=location_id
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/purchasing/open-pos")
async def purchasing_open_pos(
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).purchasing_open_pos(
            business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/payments/collected")
async def payments_collected(
    day: date | None = None,
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).payments_collected(
            business_id=ctx.business_id, day=day
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/accounting/journals-posted")
async def journals_posted(
    ctx: TenantContext = Depends(require_perms("reporting.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        return await ReportingService(session).journal_posted_count(
            business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
