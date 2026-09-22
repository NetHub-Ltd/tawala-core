"""PartyService — create party and business links (SPEC M7)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.parties import (
    LinkStatus,
    Party,
    PartyBusinessLink,
    PartyKind,
    PartyRelationship,
)
from app.models.security import Membership, MembershipStatus
from app.schemas.parties import PartyCreate, PartyLinkCreate


class PartyService:
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

    async def create_party(self, data: PartyCreate, *, user_id: UUID, business_id: UUID) -> Party:
        """Create a party and optionally caller proves membership for audit context."""
        await self._require_membership(user_id, business_id)
        try:
            kind = PartyKind(data.kind)
        except ValueError:
            kind = PartyKind.PERSON
        party = Party(
            id=uuid4(),
            kind=kind,
            display_name=data.display_name,
            primary_email=data.primary_email,
            primary_phone=data.primary_phone,
        )
        self._session.add(party)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="parties.create",
            event_type="party.created",
            resource_type="party",
            resource_id=party.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={"display_name": party.display_name, "kind": party.kind.value},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(party)
        return party

    async def link_party(
        self,
        party_id: UUID,
        data: PartyLinkCreate,
        *,
        user_id: UUID,
        business_id: UUID,
    ) -> PartyBusinessLink:
        await self._require_membership(user_id, business_id)
        party = await self._session.get(Party, party_id)
        if party is None or party.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Party not found")
        try:
            rel = PartyRelationship(data.relationship)
        except ValueError:
            rel = PartyRelationship.OTHER
        existing = (await self._session.exec(
            select(PartyBusinessLink).where(
                PartyBusinessLink.business_id == business_id,
                PartyBusinessLink.party_id == party_id,
                PartyBusinessLink.relationship == rel,
            )
        )).first()
        if existing and existing.deleted_at is None:
            raise DomainError(DomainErrorCode.CONFLICT, "Link already exists")
        link = PartyBusinessLink(
            id=uuid4(),
            business_id=business_id,
            party_id=party_id,
            relationship=rel,
            status=LinkStatus.ACTIVE,
            external_ref=data.external_ref,
        )
        self._session.add(link)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="parties.link",
            event_type="party.linked",
            resource_type="party_business_link",
            resource_id=link.id,
            business_id=business_id,
            actor_user_id=user_id,
            after={
                "party_id": str(party_id),
                "relationship": link.relationship.value,
            },
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def get_party_for_business(
        self, party_id: UUID, *, user_id: UUID, business_id: UUID
    ) -> Party:
        await self._require_membership(user_id, business_id)
        link = (await self._session.exec(
            select(PartyBusinessLink).where(
                PartyBusinessLink.party_id == party_id,
                PartyBusinessLink.business_id == business_id,
                PartyBusinessLink.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )).first()
        if link is None:
            # IDOR: do not reveal whether party exists globally
            raise DomainError(DomainErrorCode.NOT_FOUND, "Party not found")
        party = await self._session.get(Party, party_id)
        if party is None or party.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Party not found")
        return party

    async def list_links_for_business(
        self, business_id: UUID, *, user_id: UUID
    ) -> list[PartyBusinessLink]:
        await self._require_membership(user_id, business_id)
        result = await self._session.exec(
            select(PartyBusinessLink).where(
                PartyBusinessLink.business_id == business_id,
                PartyBusinessLink.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        return list(result.all())
