"""Organization routes (SPEC F.3) — permission-gated (P0)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, require_perms
from app.core_platform.organization.service import OrganizationService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.models.identity import User
from app.schemas.organization import (
    BranchCreate,
    BranchRead,
    BusinessCreate,
    BusinessRead,
    BusinessUpdate,
    LocationCreate,
    LocationRead,
)

router = APIRouter(prefix="/api/v1", tags=["organization"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.UNAUTHORIZED: 401,
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


async def get_org_service(session: AsyncSession = Depends(get_session)) -> OrganizationService:
    return OrganizationService(session)


@router.post("/businesses", response_model=BusinessRead, status_code=201)
async def create_business(
    body: BusinessCreate,
    user: User = Depends(get_current_user),
    service: OrganizationService = Depends(get_org_service),
) -> BusinessRead:
    """Bootstrap: any authenticated user may create a business and becomes Owner."""
    try:
        b = await service.create_business(body, owner_user_id=user.id)
    except DomainError as exc:
        raise _map(exc) from exc
    return BusinessRead.model_validate(b)


@router.get("/businesses/{business_id}", response_model=BusinessRead)
async def get_business(
    business_id: UUID,
    ctx: TenantContext = Depends(require_perms("organization.business.read")),
    service: OrganizationService = Depends(get_org_service),
) -> BusinessRead:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        b = await service.get_business(business_id, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return BusinessRead.model_validate(b)


@router.patch("/businesses/{business_id}", response_model=BusinessRead)
async def update_business(
    business_id: UUID,
    body: BusinessUpdate,
    ctx: TenantContext = Depends(require_perms("organization.business.update")),
    service: OrganizationService = Depends(get_org_service),
) -> BusinessRead:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        b = await service.update_business(business_id, body, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return BusinessRead.model_validate(b)


@router.post("/businesses/{business_id}/branches", response_model=BranchRead, status_code=201)
async def create_branch(
    business_id: UUID,
    body: BranchCreate,
    ctx: TenantContext = Depends(require_perms("organization.branch.create")),
    service: OrganizationService = Depends(get_org_service),
) -> BranchRead:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        b = await service.create_branch(business_id, body, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return BranchRead.model_validate(b)


@router.get("/businesses/{business_id}/branches", response_model=list[BranchRead])
async def list_branches(
    business_id: UUID,
    ctx: TenantContext = Depends(require_perms("organization.branch.read")),
    service: OrganizationService = Depends(get_org_service),
) -> list[BranchRead]:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        rows = await service.list_branches(business_id, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return [BranchRead.model_validate(r) for r in rows]


@router.post("/branches/{branch_id}/locations", response_model=LocationRead, status_code=201)
async def create_location(
    branch_id: UUID,
    body: LocationCreate,
    ctx: TenantContext = Depends(require_perms("organization.location.create")),
    service: OrganizationService = Depends(get_org_service),
) -> LocationRead:
    try:
        loc = await service.create_location(branch_id, body, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    if loc.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    return LocationRead.model_validate(loc)


@router.get("/branches/{branch_id}/locations", response_model=list[LocationRead])
async def list_locations(
    branch_id: UUID,
    ctx: TenantContext = Depends(require_perms("organization.location.read")),
    service: OrganizationService = Depends(get_org_service),
) -> list[LocationRead]:
    try:
        rows = await service.list_locations(branch_id, user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return [LocationRead.model_validate(r) for r in rows if r.business_id == ctx.business_id]
