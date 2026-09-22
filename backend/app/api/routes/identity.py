"""Identity / auth routes (SPEC F.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import get_current_user, get_identity_service
from app.core_platform.identity.service import IdentityService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.identity import User
from app.schemas.identity import TokenResponse, UserLogin, UserRead, UserRegister

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _map_error(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.UNAUTHORIZED: 401,
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
        DomainErrorCode.VALIDATION_FAILED: 422,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.post("/register", response_model=UserRead, status_code=201)
async def register(
    body: UserRegister,
    service: IdentityService = Depends(get_identity_service),
) -> User:
    try:
        return await service.register(body)
    except DomainError as exc:
        raise _map_error(exc) from exc


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLogin,
    request: Request,
    service: IdentityService = Depends(get_identity_service),
) -> TokenResponse:
    try:
        user, session, raw = await service.login(
            body,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except DomainError as exc:
        raise _map_error(exc) from exc
    return TokenResponse(
        access_token=raw,
        expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )


@router.post("/logout", status_code=204)
async def logout(
    authorization: str | None = Header(default=None),
    service: IdentityService = Depends(get_identity_service),
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    token = authorization.split(" ", 1)[1].strip()
    await service.logout(token)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
