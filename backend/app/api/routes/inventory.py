"""Inventory routes (T7) — stock levels and mutations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.inventory.service import InventoryService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.inventory import (
    StockAdjust,
    StockLevelRead,
    StockMovementRead,
    StockMutate,
    StockTransfer,
    StockTransferRead,
)

router = APIRouter(prefix="/api/v1", tags=["inventory"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.ALREADY_PROCESSED: 200,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def _require_inventory_module(session: AsyncSession, business_id: UUID) -> None:
    await EntitlementService(session).require(business_id, "module.inventory")


@router.get("/stock/levels", response_model=list[StockLevelRead])
async def list_stock_levels(
    location_id: UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_perms("inventory.stock.read")),
    session: AsyncSession = Depends(get_session),
) -> list[StockLevelRead]:
    try:
        await _require_inventory_module(session, ctx.business_id)
        rows = await InventoryService(session).list_levels(
            ctx.business_id, location_id=location_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [StockLevelRead.model_validate(r) for r in rows]


@router.get("/stock/movements", response_model=list[StockMovementRead])
async def list_stock_movements(
    product_id: UUID | None = Query(default=None),
    location_id: UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_perms("inventory.stock.read")),
    session: AsyncSession = Depends(get_session),
) -> list[StockMovementRead]:
    try:
        await _require_inventory_module(session, ctx.business_id)
        rows = await InventoryService(session).list_movements(
            ctx.business_id, product_id=product_id, location_id=location_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [StockMovementRead.model_validate(r) for r in rows]


@router.post("/stock/receive", response_model=StockMovementRead, status_code=201)
async def receive_stock(
    body: StockMutate,
    ctx: TenantContext = Depends(require_perms("inventory.stock.receive")),
    session: AsyncSession = Depends(get_session),
) -> StockMovementRead:
    try:
        await _require_inventory_module(session, ctx.business_id)
        mov = await InventoryService(session).receive(
            business_id=ctx.business_id,
            product_id=body.product_id,
            location_id=body.location_id,
            quantity=body.quantity,
            actor_user_id=ctx.actor_user_id,
            request_id=ctx.request_id,
            note=body.note,
            reference_type=body.reference_type,
            reference_id=body.reference_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return StockMovementRead.model_validate(mov)


@router.post("/stock/issue", response_model=StockMovementRead, status_code=201)
async def issue_stock(
    body: StockMutate,
    ctx: TenantContext = Depends(require_perms("inventory.stock.issue")),
    session: AsyncSession = Depends(get_session),
) -> StockMovementRead:
    try:
        await _require_inventory_module(session, ctx.business_id)
        mov = await InventoryService(session).issue(
            business_id=ctx.business_id,
            product_id=body.product_id,
            location_id=body.location_id,
            quantity=body.quantity,
            actor_user_id=ctx.actor_user_id,
            request_id=ctx.request_id,
            note=body.note,
            reference_type=body.reference_type,
            reference_id=body.reference_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return StockMovementRead.model_validate(mov)


@router.post("/stock/adjust", response_model=StockMovementRead, status_code=201)
async def adjust_stock(
    body: StockAdjust,
    ctx: TenantContext = Depends(require_perms("inventory.stock.adjust")),
    session: AsyncSession = Depends(get_session),
) -> StockMovementRead:
    try:
        await _require_inventory_module(session, ctx.business_id)
        mov = await InventoryService(session).adjust(
            business_id=ctx.business_id,
            product_id=body.product_id,
            location_id=body.location_id,
            quantity_on_hand=body.quantity_on_hand,
            actor_user_id=ctx.actor_user_id,
            request_id=ctx.request_id,
            reason_code=body.reason_code,
            note=body.note,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return StockMovementRead.model_validate(mov)


@router.post("/stock/transfer", response_model=StockTransferRead, status_code=201)
async def transfer_stock(
    body: StockTransfer,
    ctx: TenantContext = Depends(require_perms("inventory.stock.transfer")),
    session: AsyncSession = Depends(get_session),
) -> StockTransferRead:
    try:
        await _require_inventory_module(session, ctx.business_id)
        out_m, in_m = await InventoryService(session).transfer(
            business_id=ctx.business_id,
            product_id=body.product_id,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            quantity=body.quantity,
            actor_user_id=ctx.actor_user_id,
            request_id=ctx.request_id,
            note=body.note,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return StockTransferRead(
        out_movement=StockMovementRead.model_validate(out_m),
        in_movement=StockMovementRead.model_validate(in_m),
    )
