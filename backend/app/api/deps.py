"""FastAPI dependencies for Core — auth + TenantContext (P0 hardening).

Authoritative contract reference: docs/architecture/CORE_CONTRACTS.md
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.identity.service import IdentityService
from app.core_platform.security.service import AuthorizationService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session, set_tenant_guc
from app.models.identity import User


async def get_identity_service(
    session: AsyncSession = Depends(get_session),
) -> IdentityService:
    return IdentityService(session)


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    service: IdentityService = Depends(get_identity_service),
) -> User:
    token = _bearer_token(authorization)
    try:
        return await service.resolve_user(token)
    except DomainError as exc:
        if exc.code == DomainErrorCode.UNAUTHORIZED:
            raise HTTPException(status_code=401, detail=exc.message) from exc
        raise HTTPException(status_code=400, detail=exc.message) from exc


def _uuid_or_none(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


async def get_tenant_context(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    """Resolve membership + permissions + scope, then set RLS GUCs.

    business_id is taken from path or query. branch_id / location_id from query only.
    After a successful TenantContext is built, ``app.current_business_id`` is set
    for the remainder of the transaction so PostgreSQL RLS policies apply.
    """
    raw_biz = request.path_params.get("business_id") or request.query_params.get(
        "business_id"
    )
    if not raw_biz:
        raise HTTPException(
            status_code=400,
            detail="business_id is required (path or query)",
        )
    try:
        business_id = UUID(str(raw_biz))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid business_id") from exc

    branch_id = _uuid_or_none(request.query_params.get("branch_id"))
    location_id = _uuid_or_none(request.query_params.get("location_id"))

    # Allow membership lookup for this user before business GUC is known.
    await set_tenant_guc(session, business_id=None, bypass=False)
    from sqlalchemy import text

    # connection.execute avoids SQLModel session.execute deprecation on raw SQL
    conn = await session.connection()
    await conn.execute(
        text("SELECT set_config('app.current_user_id', :uid, false)"),
        {"uid": str(user.id)},
    )

    authz = AuthorizationService(session)
    try:
        ctx = await authz.build_tenant_context(
            user_id=user.id,
            business_id=business_id,
            request_id=uuid4(),
            branch_id=branch_id,
            location_id=location_id,
        )
    except DomainError as exc:
        status = {
            DomainErrorCode.FORBIDDEN: 403,
            DomainErrorCode.UNAUTHORIZED: 401,
            DomainErrorCode.NOT_FOUND: 404,
        }.get(exc.code, 400)
        raise HTTPException(status_code=status, detail=exc.message) from exc

    # Defense-in-depth: RLS policies key off this GUC for the rest of the request.
    await set_tenant_guc(session, business_id=ctx.business_id, bypass=False)
    return ctx


def require_perms(*codes: str):
    """Dependency factory: ensure TenantContext holds all listed permission codes."""

    async def _checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        authz = AuthorizationService(session=None)  # type: ignore[arg-type]
        for code in codes:
            try:
                authz.require_permission(ctx, code)
            except DomainError as exc:
                raise HTTPException(status_code=403, detail=exc.message) from exc
        return ctx

    return _checker


def require_capability(*codes: str):
    """Dependency factory: RBAC already applied via get_tenant_context path when combined.

    Use with require_perms for full chain, or after get_tenant_context.
    Checks product entitlements for the tenant business (deny by default).
    """

    async def _checker(
        ctx: TenantContext = Depends(get_tenant_context),
        session: AsyncSession = Depends(get_session),
    ) -> TenantContext:
        from app.core_platform.entitlements.service import EntitlementService

        svc = EntitlementService(session)
        for code in codes:
            try:
                await svc.require(ctx.business_id, code)
            except DomainError as exc:
                raise HTTPException(status_code=403, detail=exc.message) from exc
        return ctx

    return _checker
