"""OrganizationService — Business, Branch, Location (SPEC E.2 / M5)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.base import utc_now
from app.models.organization import (
    Branch,
    BranchStatus,
    Business,
    BusinessStatus,
    Location,
    LocationKind,
    LocationStatus,
)
from app.models.security import Membership, MembershipStatus
from app.schemas.organization import (
    BranchCreate,
    BusinessCreate,
    BusinessUpdate,
    LocationCreate,
)


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def require_active_membership(self, user_id: UUID, business_id: UUID) -> Membership:
        m = (await self._session.exec(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.business_id == business_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )).first()
        if m is None:
            raise DomainError(DomainErrorCode.FORBIDDEN, "No active membership for this business")
        return m

    async def create_business(self, data: BusinessCreate, *, owner_user_id: UUID) -> Business:
        if data.slug:
            existing = (await self._session.exec(
                select(Business).where(Business.slug == data.slug)
            )).first()
            if existing:
                raise DomainError(DomainErrorCode.CONFLICT, "Slug already in use")
        business = Business(
            id=uuid4(),
            name=data.name,
            slug=data.slug,
            status=BusinessStatus.ACTIVE,
        )
        self._session.add(business)
        await self._session.flush()
        from datetime import UTC as _UTC

        from app.core_platform.security.service import RoleService

        membership = Membership(
            id=uuid4(),
            business_id=business.id,
            user_id=owner_user_id,
            status=MembershipStatus.ACTIVE,
            activated_at=utc_now(),
        )
        self._session.add(membership)
        await self._session.flush()
        await RoleService(self._session).bootstrap_owner(business.id, membership.id)
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="organization.business.create",
            event_type="business.created",
            resource_type="business",
            resource_id=business.id,
            business_id=business.id,
            actor_user_id=owner_user_id,
            after={"name": business.name, "slug": business.slug},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(business)
        return business

    async def get_business(self, business_id: UUID, *, user_id: UUID) -> Business:
        await self.require_active_membership(user_id, business_id)
        business = await self._session.get(Business, business_id)
        if business is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Business not found")
        return business

    async def update_business(
        self, business_id: UUID, data: BusinessUpdate, *, user_id: UUID
    ) -> Business:
        business = await self.get_business(business_id, user_id=user_id)
        if data.name is not None:
            business.name = data.name
        if data.slug is not None:
            business.slug = data.slug
        business.updated_at = utc_now()
        self._session.add(business)
        await self._session.commit()
        await self._session.refresh(business)
        return business

    async def create_branch(
        self, business_id: UUID, data: BranchCreate, *, user_id: UUID
    ) -> Branch:
        await self.require_active_membership(user_id, business_id)
        branch = Branch(
            id=uuid4(),
            business_id=business_id,
            name=data.name,
            code=data.code,
            status=BranchStatus.ACTIVE,
        )
        self._session.add(branch)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="organization.branch.create",
            event_type="branch.created",
            resource_type="branch",
            resource_id=branch.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"name": branch.name, "code": branch.code},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(branch)
        return branch

    async def list_branches(self, business_id: UUID, *, user_id: UUID) -> list[Branch]:
        await self.require_active_membership(user_id, business_id)
        result = await self._session.exec(
            select(Branch).where(Branch.business_id == business_id)
        )
        return list(result.all())

    async def create_location(
        self, branch_id: UUID, data: LocationCreate, *, user_id: UUID
    ) -> Location:
        branch = await self._session.get(Branch, branch_id)
        if branch is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Branch not found")
        await self.require_active_membership(user_id, branch.business_id)
        try:
            kind = LocationKind(data.kind)
        except ValueError:
            kind = LocationKind.OTHER
        location = Location(
            id=uuid4(),
            business_id=branch.business_id,
            branch_id=branch.id,
            name=data.name,
            kind=kind,
            status=LocationStatus.ACTIVE,
        )
        self._session.add(location)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="organization.location.create",
            event_type="location.created",
            resource_type="location",
            resource_id=location.id,
            business_id=branch.business_id,
            actor_user_id=user_id,
            after={"name": location.name, "kind": location.kind.value},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(location)
        return location

    async def list_locations(self, branch_id: UUID, *, user_id: UUID) -> list[Location]:
        branch = await self._session.get(Branch, branch_id)
        if branch is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Branch not found")
        await self.require_active_membership(user_id, branch.business_id)
        result = await self._session.exec(
            select(Location).where(Location.branch_id == branch_id)
        )
        return list(result.all())
