"""CatalogService — product/service identity (no inventory) SPEC M8."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.catalog import CatalogStatus, Category, Product, Service
from app.models.security import Membership, MembershipStatus
from app.schemas.catalog import CategoryCreate, ProductCreate, ProductUpdate, ServiceCreate


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_membership(self, user_id: UUID, business_id: UUID) -> Membership:
        m = (await self._session.exec(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.business_id == business_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )).first()
        if m is None:
            raise DomainError(
                DomainErrorCode.FORBIDDEN, "No active membership for this business"
            )
        return m

    async def create_product(
        self, data: ProductCreate, *, user_id: UUID, business_id: UUID
    ) -> Product:
        from app.core_platform.shared import idempotency as idem

        await self._require_membership(user_id, business_id)
        key = idem.require_key_format(getattr(data, "idempotency_key", None))
        if key:
            prior = await idem.lookup(
                self._session, scope=str(business_id), key=key
            )
            if prior and prior.resource_id:
                existing = await self._session.get(Product, prior.resource_id)
                if existing is not None and existing.business_id == business_id:
                    return existing
        product = Product(
            id=uuid4(),
            business_id=business_id,
            name=data.name,
            sku=data.sku,
            barcode=data.barcode,
            category_id=data.category_id,
            unit=data.unit,
            status=CatalogStatus.ACTIVE,
        )
        self._session.add(product)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="catalog.product.create",
            event_type="product.created",
            resource_type="product",
            resource_id=product.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"name": product.name, "sku": product.sku},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="catalog.product.create",
                response_body={"id": str(product.id)},
                response_status=201,
                resource_id=product.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def update_product(
        self, product_id: UUID, data: ProductUpdate, *, user_id: UUID, business_id: UUID
    ) -> Product:
        await self._require_membership(user_id, business_id)
        product = await self._session.get(Product, product_id)
        if (
            product is None
            or product.deleted_at is not None
            or product.business_id != business_id
        ):
            raise DomainError(DomainErrorCode.NOT_FOUND, "Product not found")
        if data.name is not None:
            product.name = data.name
        if data.sku is not None:
            product.sku = data.sku
        if data.barcode is not None:
            product.barcode = data.barcode
        if data.category_id is not None:
            product.category_id = data.category_id
        if data.unit is not None:
            product.unit = data.unit
        if data.status is not None:
            product.status = CatalogStatus(data.status)
        product.touch()
        self._session.add(product)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="catalog.product.update",
            event_type="product.updated",
            resource_type="product",
            resource_id=product.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"name": product.name, "sku": product.sku, "status": product.status.value},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def get_product(
        self, product_id: UUID, *, user_id: UUID, business_id: UUID
    ) -> Product:
        await self._require_membership(user_id, business_id)
        product = await self._session.get(Product, product_id)
        if (
            product is None
            or product.deleted_at is not None
            or product.business_id != business_id
        ):
            raise DomainError(DomainErrorCode.NOT_FOUND, "Product not found")
        return product

    async def list_products(
        self, *, user_id: UUID, business_id: UUID
    ) -> list[Product]:
        await self._require_membership(user_id, business_id)
        result = await self._session.exec(
            select(Product).where(
                Product.business_id == business_id,
                Product.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        return list(result.all())

    async def create_service(
        self, data: ServiceCreate, *, user_id: UUID, business_id: UUID
    ) -> Service:
        await self._require_membership(user_id, business_id)
        service = Service(
            id=uuid4(),
            business_id=business_id,
            name=data.name,
            code=data.code,
            status=CatalogStatus.ACTIVE,
        )
        self._session.add(service)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="catalog.service.create",
            event_type="service.created",
            resource_type="service",
            resource_id=service.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"name": service.name, "code": service.code},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(service)
        return service

    async def get_service(
        self, service_id: UUID, *, user_id: UUID, business_id: UUID
    ) -> Service:
        await self._require_membership(user_id, business_id)
        service = await self._session.get(Service, service_id)
        if (
            service is None
            or service.deleted_at is not None
            or service.business_id != business_id
        ):
            raise DomainError(DomainErrorCode.NOT_FOUND, "Service not found")
        return service


    async def create_category(
        self, data: CategoryCreate, *, user_id: UUID, business_id: UUID
    ) -> Category:
        await self._require_membership(user_id, business_id)
        category = Category(
            id=uuid4(),
            business_id=business_id,
            name=data.name,
            parent_id=data.parent_id,
        )
        self._session.add(category)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="catalog.category.create",
            event_type="category.created",
            resource_type="category",
            resource_id=category.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"name": category.name},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def list_categories(
        self, *, user_id: UUID, business_id: UUID
    ) -> list[Category]:
        await self._require_membership(user_id, business_id)
        result = await self._session.exec(
            select(Category).where(
                Category.business_id == business_id,
                Category.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        return list(result.all())
