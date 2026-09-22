"""Business configuration routes (#263)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.configuration.service import ConfigService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.configuration import ConfigRead, ConfigSet

router = APIRouter(prefix="/api/v1", tags=["configuration"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.put("/config", response_model=ConfigRead)
async def set_config(
    body: ConfigSet,
    ctx: TenantContext = Depends(require_perms("organization.config.manage")),
    session: AsyncSession = Depends(get_session),
) -> ConfigRead:
    try:
        row = await ConfigService(session).set(
            ctx.business_id,
            body.key,
            body.value,
            actor_user_id=ctx.actor_user_id,
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ConfigRead.model_validate(row)


@router.get("/config/{key}", response_model=ConfigRead)
async def get_config(
    key: str,
    ctx: TenantContext = Depends(require_perms("organization.config.manage")),
    session: AsyncSession = Depends(get_session),
) -> ConfigRead:
    try:
        row = await ConfigService(session).require(ctx.business_id, key)
    except DomainError as exc:
        raise _map(exc) from exc
    return ConfigRead.model_validate(row)
