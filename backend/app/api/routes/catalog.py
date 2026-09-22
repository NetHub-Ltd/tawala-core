"""Catalog routes — permission-gated, no stock (P0)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_perms
from app.core_platform.catalog.service import CatalogService
from app.core_platform.entitlements.service import EntitlementService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.db.session import get_session
from app.schemas.catalog import (
    CategoryCreate,
    CategoryRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ServiceCreate,
    ServiceRead,
)

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _map(exc: DomainError) -> HTTPException:
    status = {
        DomainErrorCode.CONFLICT: 409,
        DomainErrorCode.FORBIDDEN: 403,
        DomainErrorCode.NOT_FOUND: 404,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.message)


@router.post("/products", response_model=ProductRead, status_code=201)
async def create_product(
    body: ProductCreate,
    ctx: TenantContext = Depends(require_perms("catalog.product.create")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    try:
        await EntitlementService(session).require(ctx.business_id, "module.catalog")
    except DomainError as exc:
        raise _map(exc) from exc
    try:
        p = await CatalogService(session).create_product(
            body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ProductRead.model_validate(p)


@router.patch("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: UUID,
    body: ProductUpdate,
    ctx: TenantContext = Depends(require_perms("catalog.product.update")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    try:
        p = await CatalogService(session).update_product(
            product_id, body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ProductRead.model_validate(p)


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: UUID,
    ctx: TenantContext = Depends(require_perms("catalog.product.read")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    try:
        p = await CatalogService(session).get_product(
            product_id, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ProductRead.model_validate(p)


@router.get("/products", response_model=list[ProductRead])
async def list_products(
    ctx: TenantContext = Depends(require_perms("catalog.product.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ProductRead]:
    try:
        rows = await CatalogService(session).list_products(
            user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [ProductRead.model_validate(r) for r in rows]


@router.post("/services", response_model=ServiceRead, status_code=201)
async def create_service(
    body: ServiceCreate,
    ctx: TenantContext = Depends(require_perms("catalog.service.create")),
    session: AsyncSession = Depends(get_session),
) -> ServiceRead:
    try:
        s = await CatalogService(session).create_service(
            body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ServiceRead.model_validate(s)


@router.get("/services/{service_id}", response_model=ServiceRead)
async def get_service(
    service_id: UUID,
    ctx: TenantContext = Depends(require_perms("catalog.service.read")),
    session: AsyncSession = Depends(get_session),
) -> ServiceRead:
    try:
        s = await CatalogService(session).get_service(
            service_id, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return ServiceRead.model_validate(s)


@router.post("/categories", response_model=CategoryRead, status_code=201)
async def create_category(
    body: CategoryCreate,
    ctx: TenantContext = Depends(require_perms("catalog.category.create")),
    session: AsyncSession = Depends(get_session),
) -> CategoryRead:
    try:
        c = await CatalogService(session).create_category(
            body, user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return CategoryRead.model_validate(c)


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    ctx: TenantContext = Depends(require_perms("catalog.category.read")),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryRead]:
    try:
        rows = await CatalogService(session).list_categories(
            user_id=ctx.actor_user_id, business_id=ctx.business_id
        )
    except DomainError as exc:
        raise _map(exc) from exc
    return [CategoryRead.model_validate(r) for r in rows]
