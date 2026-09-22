"""Sales routes (T8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.sales.service import SalesService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.models.sales import SalesDocumentType
from app.schemas.sales import (
    FinalizeBody,
    PaymentCreate,
    SalesDocumentCreate,
    SalesDocumentRead,
)

router = APIRouter(prefix="/api/v1", tags=["sales"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.ALREADY_PROCESSED: 409,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def _mod(session: AsyncSession, business_id: UUID) -> None:
    await EntitlementService(session).require(business_id, "module.sales")


@router.post("/sales/documents", response_model=SalesDocumentRead, status_code=201)
async def create_sales_document(
    body: SalesDocumentCreate,
    ctx: TenantContext = Depends(require_perms("sales.document.manage")),
    session: AsyncSession = Depends(get_session),
) -> SalesDocumentRead:
    try:
        await _mod(session, ctx.business_id)
        dtype = SalesDocumentType(body.document_type)
        doc = await SalesService(session).create_document(
            business_id=ctx.business_id,
            document_type=dtype,
            party_id=body.party_id,
            branch_id=body.branch_id,
            location_id=body.location_id,
            notes=body.notes,
            source_document_id=body.source_document_id,
            lines=[ln.model_dump() for ln in body.lines],
            actor_user_id=ctx.actor_user_id,
            currency=body.currency,
        )
    except (DomainError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise _map(exc) from exc
    return SalesDocumentRead.model_validate(doc)


@router.post("/sales/quotes/{quote_id}/convert-order", response_model=SalesDocumentRead)
async def convert_quote(
    quote_id: UUID,
    ctx: TenantContext = Depends(require_perms("sales.document.manage")),
    session: AsyncSession = Depends(get_session),
) -> SalesDocumentRead:
    try:
        await _mod(session, ctx.business_id)
        doc = await SalesService(session).convert_quote_to_order(
            business_id=ctx.business_id, quote_id=quote_id, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return SalesDocumentRead.model_validate(doc)


@router.post("/sales/orders/{order_id}/convert-invoice", response_model=SalesDocumentRead)
async def convert_order(
    order_id: UUID,
    ctx: TenantContext = Depends(require_perms("sales.document.manage")),
    session: AsyncSession = Depends(get_session),
) -> SalesDocumentRead:
    try:
        await _mod(session, ctx.business_id)
        doc = await SalesService(session).convert_order_to_invoice(
            business_id=ctx.business_id, order_id=order_id, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return SalesDocumentRead.model_validate(doc)


@router.post("/sales/invoices/{invoice_id}/finalize", response_model=SalesDocumentRead)
async def finalize_invoice(
    invoice_id: UUID,
    body: FinalizeBody | None = None,
    ctx: TenantContext = Depends(require_perms("sales.document.finalize")),
    session: AsyncSession = Depends(get_session),
) -> SalesDocumentRead:
    body = body or FinalizeBody()
    try:
        await _mod(session, ctx.business_id)
        doc = await SalesService(session).finalize_invoice(
            business_id=ctx.business_id,
            invoice_id=invoice_id,
            actor_user_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return SalesDocumentRead.model_validate(doc)


@router.post("/sales/invoices/{invoice_id}/payments", status_code=201)
async def record_payment(
    invoice_id: UUID,
    body: PaymentCreate,
    ctx: TenantContext = Depends(require_perms("sales.payment.record")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        pay = await SalesService(session).record_payment(
            business_id=ctx.business_id,
            invoice_id=invoice_id,
            amount=body.amount,
            method=body.method,
            reference=body.reference,
            actor_user_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return {"id": str(pay.id), "amount": str(pay.amount)}


@router.post("/sales/returns/{return_id}/finalize", response_model=SalesDocumentRead)
async def finalize_return(
    return_id: UUID,
    body: FinalizeBody | None = None,
    ctx: TenantContext = Depends(require_perms("sales.document.finalize")),
    session: AsyncSession = Depends(get_session),
) -> SalesDocumentRead:
    body = body or FinalizeBody()
    try:
        await _mod(session, ctx.business_id)
        doc = await SalesService(session).finalize_return(
            business_id=ctx.business_id,
            return_id=return_id,
            actor_user_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return SalesDocumentRead.model_validate(doc)
