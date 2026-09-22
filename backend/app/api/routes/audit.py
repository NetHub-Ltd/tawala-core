"""Audit list — requires audit.read (P0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.audit.service import AuditService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.audit import AuditRecordRead

router = APIRouter(prefix="/api/v1", tags=["audit"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/audit-records", response_model=list[AuditRecordRead])
async def list_audit_records(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_perms("audit.read")),
    session: AsyncSession = Depends(get_session),
) -> list[AuditRecordRead]:
    try:
        rows = await AuditService(session).list_for_business(
            ctx.business_id, limit=limit
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [AuditRecordRead.model_validate(r) for r in rows]
