"""CrmService — customer intelligence on Party (T11). Read sales for history; no sales/accounting writes."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.base import utc_now
from app.models.crm import CreditStatus, CustomerActivity, CustomerNote, CustomerProfile
from app.models.parties import (
    LinkStatus,
    Party,
    PartyBusinessLink,
    PartyRelationship,
)
from app.models.sales import SalesDocument, SalesDocumentStatus, SalesDocumentType, SalesLine


class CrmService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_customer_link(
        self, business_id: UUID, party_id: UUID
    ) -> PartyBusinessLink:
        link = (
            await self._session.exec(
                select(PartyBusinessLink).where(
                    PartyBusinessLink.business_id == business_id,
                    PartyBusinessLink.party_id == party_id,
                    PartyBusinessLink.relationship == PartyRelationship.CUSTOMER,
                    PartyBusinessLink.status == LinkStatus.ACTIVE,
                    PartyBusinessLink.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if link is None:
            raise DomainError(
                DomainErrorCode.NOT_FOUND,
                "No active customer link for party in this business",
            )
        return link

    async def _log(
        self,
        *,
        business_id: UUID,
        party_id: UUID,
        activity_type: str,
        summary: str,
        actor_user_id: UUID | None,
    ) -> None:
        self._session.add(
            CustomerActivity(
                id=uuid4(),
                business_id=business_id,
                party_id=party_id,
                activity_type=activity_type,
                summary=summary,
                actor_user_id=actor_user_id,
                occurred_at=utc_now(),
            )
        )

    async def get_or_create_profile(
        self,
        *,
        business_id: UUID,
        party_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> CustomerProfile:
        await self._require_customer_link(business_id, party_id)
        row = (
            await self._session.exec(
                select(CustomerProfile).where(
                    CustomerProfile.business_id == business_id,
                    CustomerProfile.party_id == party_id,
                    CustomerProfile.deleted_at.is_(None),  # type: ignore[attr-defined]
                )
            )
        ).first()
        if row is not None:
            return row
        row = CustomerProfile(
            id=uuid4(),
            business_id=business_id,
            party_id=party_id,
            credit_status=CreditStatus.NONE,
            credit_limit=Decimal("0"),
        )
        self._session.add(row)
        await self._log(
            business_id=business_id,
            party_id=party_id,
            activity_type="profile_created",
            summary="Customer profile created",
            actor_user_id=actor_user_id,
        )
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="crm.profile.create",
            event_type="crm.profile.created",
            resource_type="customer_profile",
            resource_id=row.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            payload={"party_id": str(party_id)},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def update_profile(
        self,
        *,
        business_id: UUID,
        party_id: UUID,
        credit_status: CreditStatus | None = None,
        credit_limit: Decimal | None = None,
        segment: str | None = None,
        tags: str | None = None,
        preferred_branch_id: UUID | None = None,
        notes_summary: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> CustomerProfile:
        profile = await self.get_or_create_profile(
            business_id=business_id, party_id=party_id, actor_user_id=actor_user_id
        )
        if credit_status is not None:
            profile.credit_status = credit_status
            await self._log(
                business_id=business_id,
                party_id=party_id,
                activity_type="credit_updated",
                summary=f"Credit status → {credit_status.value}",
                actor_user_id=actor_user_id,
            )
        if credit_limit is not None:
            if credit_limit < 0:
                raise DomainError(
                    DomainErrorCode.VALIDATION_FAILED, "credit_limit cannot be negative"
                )
            profile.credit_limit = credit_limit
        if segment is not None:
            profile.segment = segment
        if tags is not None:
            profile.tags = tags
        if preferred_branch_id is not None:
            profile.preferred_branch_id = preferred_branch_id
        if notes_summary is not None:
            profile.notes_summary = notes_summary
        profile.touch()
        self._session.add(profile)
        await self._session.commit()
        await self._session.refresh(profile)
        return profile

    async def add_note(
        self,
        *,
        business_id: UUID,
        party_id: UUID,
        body: str,
        actor_user_id: UUID | None = None,
    ) -> CustomerNote:
        await self._require_customer_link(business_id, party_id)
        if not body or not body.strip():
            raise DomainError(DomainErrorCode.VALIDATION_FAILED, "note body required")
        note = CustomerNote(
            id=uuid4(),
            business_id=business_id,
            party_id=party_id,
            body=body.strip(),
            actor_user_id=actor_user_id,
        )
        self._session.add(note)
        await self._log(
            business_id=business_id,
            party_id=party_id,
            activity_type="note_added",
            summary=body.strip()[:200],
            actor_user_id=actor_user_id,
        )
        await self._session.commit()
        await self._session.refresh(note)
        return note

    async def list_notes(
        self, business_id: UUID, party_id: UUID
    ) -> list[CustomerNote]:
        await self._require_customer_link(business_id, party_id)
        return list(
            (
                await self._session.exec(
                    select(CustomerNote).where(
                        CustomerNote.business_id == business_id,
                        CustomerNote.party_id == party_id,
                        CustomerNote.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )

    async def list_activity(
        self, business_id: UUID, party_id: UUID, *, limit: int = 50
    ) -> list[CustomerActivity]:
        await self._require_customer_link(business_id, party_id)
        return list(
            (
                await self._session.exec(
                    select(CustomerActivity)
                    .where(
                        CustomerActivity.business_id == business_id,
                        CustomerActivity.party_id == party_id,
                        CustomerActivity.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                    .order_by(CustomerActivity.occurred_at.desc())  # type: ignore[attr-defined]
                    .limit(limit)
                )
            ).all()
        )

    async def purchase_history(
        self, business_id: UUID, party_id: UUID, *, limit: int = 50
    ) -> list[dict]:
        """Projection from authoritative Sales documents — CRM does not store sales rows."""
        await self._require_customer_link(business_id, party_id)
        docs = list(
            (
                await self._session.exec(
                    select(SalesDocument)
                    .where(
                        SalesDocument.business_id == business_id,
                        SalesDocument.party_id == party_id,
                        SalesDocument.document_type == SalesDocumentType.INVOICE,
                        SalesDocument.status == SalesDocumentStatus.FINALIZED,
                        SalesDocument.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                    .order_by(SalesDocument.finalized_at.desc())  # type: ignore[attr-defined]
                    .limit(limit)
                )
            ).all()
        )
        out: list[dict] = []
        for doc in docs:
            lines = list(
                (
                    await self._session.exec(
                        select(SalesLine).where(
                            SalesLine.document_id == doc.id,
                            SalesLine.deleted_at.is_(None),  # type: ignore[attr-defined]
                        )
                    )
                ).all()
            )
            total = sum((ln.line_total for ln in lines), Decimal("0"))
            out.append(
                {
                    "document_id": str(doc.id),
                    "document_number": doc.document_number,
                    "finalized_at": doc.finalized_at.isoformat() if doc.finalized_at else None,
                    "currency": doc.currency,
                    "total": str(total),
                    "line_count": len(lines),
                }
            )
        return out

    async def get_party_identity(
        self, business_id: UUID, party_id: UUID
    ) -> Party:
        """Read Party through customer link — no second identity store."""
        await self._require_customer_link(business_id, party_id)
        party = await self._session.get(Party, party_id)
        if party is None or party.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Party not found")
        return party
