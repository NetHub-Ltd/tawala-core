"""Entitlement routes (T5) — product capability grants per business."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.entitlements import EntitlementGrant, EntitlementRead

router = APIRouter(prefix="/api/v1", tags=["entitlements"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
        DomainErrorCode.CONFLICT: 409,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/entitlements", response_model=list[EntitlementRead])
async def list_entitlements(
    ctx: TenantContext = Depends(require_perms("organization.entitlements.read")),
    session: AsyncSession = Depends(get_session),
) -> list[EntitlementRead]:
    rows = await EntitlementService(session).list_for_business(ctx.business_id)
    return [EntitlementRead.model_validate(r) for r in rows]


@router.put("/entitlements/{code}", response_model=EntitlementRead)
async def grant_entitlement(
    code: str,
    body: EntitlementGrant,
    ctx: TenantContext = Depends(require_perms("organization.entitlements.manage")),
    session: AsyncSession = Depends(get_session),
) -> EntitlementRead:
    if body.code != code:
        raise HTTPException(status_code=400, detail="path code must match body.code")
    try:
        await EntitlementService(session).ensure_catalog_seeded()
        row = await EntitlementService(session).grant(
            ctx.business_id,
            code,
            limit_value=body.limit_value,
            source=body.source,
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return EntitlementRead.model_validate(row)


@router.delete("/entitlements/{code}", status_code=204)
async def revoke_entitlement(
    code: str,
    ctx: TenantContext = Depends(require_perms("organization.entitlements.manage")),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await EntitlementService(session).revoke(
            ctx.business_id, code, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
