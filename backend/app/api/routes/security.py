"""Membership and role routes — permission-gated (P0)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, get_tenant_context, require_perms
from app.core_platform.security.service import (
    AuthorizationService,
    MembershipService,
    RoleService,
)
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.models.identity import User
from app.schemas.security import (
    MembershipInvite,
    MembershipRead,
    PermissionAttach,
    RoleAssign,
    RoleCreate,
    RoleRead,
    ScopeAssign,
    ScopeRead,
)

router = APIRouter(prefix="/api/v1", tags=["security"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.UNAUTHORIZED: 401,
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.post(
    "/businesses/{business_id}/memberships",
    response_model=MembershipRead,
    status_code=201,
)
async def invite_membership(
    business_id: UUID,
    body: MembershipInvite,
    ctx: TenantContext = Depends(require_perms("security.membership.invite")),
    session: AsyncSession = Depends(get_session),
) -> MembershipRead:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        m = await MembershipService(session).invite(
            business_id,
            body.user_id,
            actor_id=ctx.actor_user_id,
            idempotency_key=body.idempotency_key,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return MembershipRead.model_validate(m)


@router.get(
    "/businesses/{business_id}/memberships",
    response_model=list[MembershipRead],
)
async def list_memberships(
    business_id: UUID,
    ctx: TenantContext = Depends(require_perms("security.membership.read")),
    session: AsyncSession = Depends(get_session),
) -> list[MembershipRead]:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        rows = await MembershipService(session).list_for_business(business_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return [MembershipRead.model_validate(r) for r in rows]


@router.post("/memberships/{membership_id}/activate", response_model=MembershipRead)
async def activate_membership(
    membership_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MembershipRead:
    try:
        m = await MembershipService(session).activate(membership_id)
    except DomainError as exc:
        raise _map(exc) from exc
    return MembershipRead.model_validate(m)


@router.post("/memberships/{membership_id}/suspend", response_model=MembershipRead)
async def suspend_membership(
    membership_id: UUID,
    ctx: TenantContext = Depends(require_perms("security.membership.suspend")),
    session: AsyncSession = Depends(get_session),
) -> MembershipRead:
    try:
        m = await MembershipService(session).suspend(membership_id, actor_user_id=ctx.actor_user_id)
    except DomainError as exc:
        raise _map(exc) from exc
    if m.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    return MembershipRead.model_validate(m)


@router.post("/memberships/{membership_id}/revoke", response_model=MembershipRead)
async def revoke_membership(
    membership_id: UUID,
    ctx: TenantContext = Depends(require_perms("security.membership.revoke")),
    session: AsyncSession = Depends(get_session),
) -> MembershipRead:
    try:
        m = await MembershipService(session).revoke(
            membership_id, actor_user_id=ctx.actor_user_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    if m.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    return MembershipRead.model_validate(m)


@router.post("/businesses/{business_id}/roles", response_model=RoleRead, status_code=201)
async def create_role(
    business_id: UUID,
    body: RoleCreate,
    ctx: TenantContext = Depends(require_perms("security.role.manage")),
    session: AsyncSession = Depends(get_session),
) -> RoleRead:
    if ctx.business_id != business_id:
        raise HTTPException(status_code=403, detail="Business context mismatch")
    try:
        role = await RoleService(session).create_role(business_id, body.name)
    except DomainError as exc:
        raise _map(exc) from exc
    return RoleRead.model_validate(role)


@router.post("/roles/{role_id}/permissions", status_code=204)
async def attach_permission(
    role_id: UUID,
    body: PermissionAttach,
    ctx: TenantContext = Depends(require_perms("security.role.manage")),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await RoleService(session).attach_permission(role_id, body.permission_code)
    except DomainError as exc:
        raise _map(exc) from exc


@router.post("/memberships/{membership_id}/roles", status_code=204)
async def assign_role(
    membership_id: UUID,
    body: RoleAssign,
    ctx: TenantContext = Depends(require_perms("security.role.assign")),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await RoleService(session).assign_role(
            membership_id, body.role_id,
            actor_user_id=ctx.actor_user_id, business_id=ctx.business_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc


@router.get("/me/permissions")
async def my_permissions(
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    return {
        "business_id": str(ctx.business_id),
        "permissions": sorted(ctx.permissions),
        "membership_id": str(ctx.membership_id),
    }


@router.post("/scopes", response_model=ScopeRead, status_code=201)
async def create_scope(
    body: ScopeAssign,
    ctx: TenantContext = Depends(require_perms("security.scope.manage")),
    session: AsyncSession = Depends(get_session),
) -> ScopeRead:
    try:
        row = await AuthorizationService(session).assign_scope(
            membership_id=body.membership_id,
            branch_id=body.branch_id,
            location_id=body.location_id,
            actor_user_id=ctx.actor_user_id,
            business_id=ctx.business_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ScopeRead.model_validate(row)


@router.get("/memberships/{membership_id}/scopes", response_model=list[ScopeRead])
async def list_scopes(
    membership_id: UUID,
    ctx: TenantContext = Depends(require_perms("security.scope.manage")),
    session: AsyncSession = Depends(get_session),
) -> list[ScopeRead]:
    try:
        rows = await AuthorizationService(session).list_scopes(
            membership_id=membership_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [ScopeRead.model_validate(r) for r in rows]
