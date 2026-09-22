"""CRM routes (T11) — customer intelligence; no sales/accounting mutation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.crm.service import CrmService
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.models.crm import CreditStatus
from app.schemas.crm import NoteCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/api/v1", tags=["crm"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 400,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def _mod(session: AsyncSession, business_id: UUID) -> None:
    await EntitlementService(session).require(business_id, "module.crm")


@router.get("/crm/customers/{party_id}/profile", response_model=ProfileRead)
async def get_profile(
    party_id: UUID,
    ctx: TenantContext = Depends(require_perms("crm.customer.read")),
    session: AsyncSession = Depends(get_session),
) -> ProfileRead:
    try:
        await _mod(session, ctx.business_id)
        p = await CrmService(session).get_or_create_profile(
            business_id=ctx.business_id,
            party_id=party_id,
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ProfileRead.model_validate(p)


@router.patch("/crm/customers/{party_id}/profile", response_model=ProfileRead)
async def update_profile(
    party_id: UUID,
    body: ProfileUpdate,
    ctx: TenantContext = Depends(require_perms("crm.customer.manage")),
    session: AsyncSession = Depends(get_session),
) -> ProfileRead:
    try:
        await _mod(session, ctx.business_id)
        status = CreditStatus(body.credit_status) if body.credit_status else None
        p = await CrmService(session).update_profile(
            business_id=ctx.business_id,
            party_id=party_id,
            credit_status=status,
            credit_limit=body.credit_limit,
            segment=body.segment,
            tags=body.tags,
            preferred_branch_id=body.preferred_branch_id,
            notes_summary=body.notes_summary,
            actor_user_id=ctx.actor_user_id,
        )
    except (DomainError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise _map(exc) from exc
    return ProfileRead.model_validate(p)


@router.post("/crm/customers/{party_id}/notes", status_code=201)
async def add_note(
    party_id: UUID,
    body: NoteCreate,
    ctx: TenantContext = Depends(require_perms("crm.customer.manage")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await _mod(session, ctx.business_id)
        n = await CrmService(session).add_note(
            business_id=ctx.business_id,
            party_id=party_id,
            body=body.body,
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return {"id": str(n.id)}


@router.get("/crm/customers/{party_id}/notes")
async def list_notes(
    party_id: UUID,
    ctx: TenantContext = Depends(require_perms("crm.customer.read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    try:
        await _mod(session, ctx.business_id)
        rows = await CrmService(session).list_notes(ctx.business_id, party_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return [{"id": str(r.id), "body": r.body} for r in rows]


@router.get("/crm/customers/{party_id}/activity")
async def list_activity(
    party_id: UUID,
    ctx: TenantContext = Depends(require_perms("crm.customer.read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    try:
        await _mod(session, ctx.business_id)
        rows = await CrmService(session).list_activity(ctx.business_id, party_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return [
        {
            "id": str(r.id),
            "activity_type": r.activity_type,
            "summary": r.summary,
            "occurred_at": r.occurred_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/crm/customers/{party_id}/purchase-history")
async def purchase_history(
    party_id: UUID,
    ctx: TenantContext = Depends(require_perms("crm.customer.read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    try:
        await _mod(session, ctx.business_id)
        return await CrmService(session).purchase_history(ctx.business_id, party_id)
    except DomainError as exc:
        raise _map(exc) from exc
