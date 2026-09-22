"""Party routes — permission-gated (P0)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.parties.service import PartyService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.parties import PartyCreate, PartyLinkCreate, PartyLinkRead, PartyRead

router = APIRouter(prefix="/api/v1", tags=["parties"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.post("/parties", response_model=PartyRead, status_code=201)
async def create_party(
    body: PartyCreate,
    ctx: TenantContext = Depends(require_perms("parties.create")),
    session: AsyncSession = Depends(get_session),
) -> PartyRead:
    try:
        party = await PartyService(session).create_party(
            body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PartyRead.model_validate(party)


@router.post("/parties/{party_id}/links", response_model=PartyLinkRead, status_code=201)
async def link_party(
    party_id: UUID,
    body: PartyLinkCreate,
    ctx: TenantContext = Depends(require_perms("parties.link")),
    session: AsyncSession = Depends(get_session),
) -> PartyLinkRead:
    try:
        link = await PartyService(session).link_party(
            party_id, body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PartyLinkRead.model_validate(link)


@router.get("/parties/{party_id}", response_model=PartyRead)
async def get_party(
    party_id: UUID,
    ctx: TenantContext = Depends(require_perms("parties.read")),
    session: AsyncSession = Depends(get_session),
) -> PartyRead:
    try:
        party = await PartyService(session).get_party_for_business(
            party_id, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return PartyRead.model_validate(party)


@router.get(
    "/businesses/{business_id}/parties",
    response_model=list[PartyLinkRead],
)
async def list_business_parties(
    business_id: UUID,
    ctx: TenantContext = Depends(require_perms("parties.read")),
    session: AsyncSession = Depends(get_session),
) -> list[PartyLinkRead]:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        links = await PartyService(session).list_links_for_business(
            business_id, user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [PartyLinkRead.model_validate(x) for x in links]
