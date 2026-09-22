"""Purchasing routes (T9)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.purchasing.service import PurchasingService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.purchasing import (
    FinalizeBody,
    GoodsReceiptCreate,
    GoodsReceiptRead,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchasePaymentCreate,
)

router = APIRouter(prefix="/api/v1", tags=["purchasing"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
        DomainErrorCode.ALREADY_PROCESSED: 409,
        DomainErrorCode.CONFLICT: 409,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def _mod(session: AsyncSession, business_id: UUID) -> None:
    await EntitlementService(session).require(business_id, "module.purchasing")


@router.post("/purchasing/orders", response_model=PurchaseOrderRead, status_code=201)
async def create_po(
    body: PurchaseOrderCreate,
    ctx: TenantContext = Depends(require_perms("purchasing.order.manage")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    try:
        await _mod(session, ctx.business_id)
        po = await PurchasingService(session).create_order(
            business_id=ctx.business_id,
            party_id=body.party_id,
            branch_id=body.branch_id,
            location_id=body.location_id,
            notes=body.notes,
            currency=body.currency,
            lines=[ln.model_dump() for ln in body.lines],
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PurchaseOrderRead.model_validate(po)


@router.post("/purchasing/orders/{po_id}/confirm", response_model=PurchaseOrderRead)
async def confirm_po(
    po_id: UUID,
    ctx: TenantContext = Depends(require_perms("purchasing.order.manage")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    try:
        await _mod(session, ctx.business_id)
        po = await PurchasingService(session).confirm_order(
            business_id=ctx.business_id, po_id=po_id, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PurchaseOrderRead.model_validate(po)


@router.post("/purchasing/orders/{po_id}/cancel", response_model=PurchaseOrderRead)
async def cancel_po(
    po_id: UUID,
    ctx: TenantContext = Depends(require_perms("purchasing.order.manage")),
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderRead:
    try:
        await _mod(session, ctx.business_id)
        po = await PurchasingService(session).cancel_order(
            business_id=ctx.business_id, po_id=po_id, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PurchaseOrderRead.model_validate(po)


@router.post("/purchasing/receipts", response_model=GoodsReceiptRead, status_code=201)
async def create_receipt(
    body: GoodsReceiptCreate,
    ctx: TenantContext = Depends(require_perms("purchasing.receive")),
    session: AsyncSession = Depends(get_session),
) -> GoodsReceiptRead:
    try:
        await _mod(session, ctx.business_id)
        grn = await PurchasingService(session).create_receipt(
            business_id=ctx.business_id,
            purchase_order_id=body.purchase_order_id,
            location_id=body.location_id,
            lines=[ln.model_dump() for ln in body.lines],
            notes=body.notes,
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return GoodsReceiptRead.model_validate(grn)


@router.post("/purchasing/receipts/{receipt_id}/finalize", response_model=GoodsReceiptRead)
async def finalize_receipt(
    receipt_id: UUID,
    body: FinalizeBody | None = None,
    ctx: TenantContext = Depends(require_perms("purchasing.receive")),
    session: AsyncSession = Depends(get_session),
) -> GoodsReceiptRead:
    body = body or FinalizeBody()
    try:
        await _mod(session, ctx.business_id)
        grn = await PurchasingService(session).finalize_receipt(
            business_id=ctx.business_id,
            receipt_id=receipt_id,
            actor_user_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return GoodsReceiptRead.model_validate(grn)


@router.post("/purchasing/orders/{po_id}/payments", status_code=201)
async def record_payment(
    po_id: UUID,
    body: PurchasePaymentCreate,
    ctx: TenantContext = Depends(require_perms("purchasing.payment.record")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        pay = await PurchasingService(session).record_payment(
            business_id=ctx.business_id,
            purchase_order_id=po_id,
            amount=body.amount,
            method=body.method,
            reference=body.reference,
            actor_user_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return {"id": str(pay.id), "amount": str(pay.amount)}
