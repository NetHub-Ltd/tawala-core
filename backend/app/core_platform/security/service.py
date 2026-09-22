"""Membership, roles, permissions, authorization (SPEC M6 + P0 hardening)."""

from __future__ import annotations

from datetime import datetime

from app.models.base import utc_now
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.security.permissions_seed import SYSTEM_PERMISSIONS
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext
from app.models.security import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Permission,
    Role,
    RolePermission,
    ScopeAssignment,
)


class MembershipService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(
        self, user_id: UUID, business_id: UUID
    ) -> Membership | None:
        return (await self._session.exec(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.business_id == business_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )).first()

    async def invite(
        self,
        business_id: UUID,
        user_id: UUID,
        *,
        actor_id: UUID,
        idempotency_key: str | None = None,
    ) -> Membership:
        from app.core_platform.shared import idempotency as idem

        key = idem.require_key_format(idempotency_key)
        if key:
            prior = await idem.lookup(
                self._session, scope=str(business_id), key=key
            )
            if prior and prior.resource_id:
                m_prior = await self._session.get(Membership, prior.resource_id)
                if m_prior is not None:
                    return m_prior
        existing = (await self._session.exec(
            select(Membership).where(
                Membership.business_id == business_id,
                Membership.user_id == user_id,
            )
        )).first()
        if existing and existing.status not in (
            MembershipStatus.REVOKED,
            MembershipStatus.SUSPENDED,
        ):
            raise DomainError(DomainErrorCode.CONFLICT, "Membership already exists")
        if existing:
            existing.status = MembershipStatus.INVITED
            existing.invited_at = utc_now()
            existing.revoked_at = None
            existing.touch()
            self._session.add(existing)
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        m = Membership(
            id=uuid4(),
            business_id=business_id,
            user_id=user_id,
            status=MembershipStatus.INVITED,
            invited_at=utc_now(),
        )
        self._session.add(m)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="security.membership.invite",
            event_type="membership.invited",
            resource_type="membership",
            resource_id=m.id,
            business_id=business_id,
            actor_user_id=actor_id,
            after={"user_id": str(user_id), "status": m.status.value},
            commit=False,
        )
        if key:
            await idem.store(
                self._session,
                scope=str(business_id),
                key=key,
                operation="security.membership.invite",
                response_body={"id": str(m.id)},
                response_status=201,
                resource_id=m.id,
                commit=False,
            )
        await self._session.commit()
        await self._session.refresh(m)
        return m

    async def activate(self, membership_id: UUID) -> Membership:
        m = await self._session.get(Membership, membership_id)
        if m is None or m.deleted_at is not None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Membership not found")
        if m.status == MembershipStatus.REVOKED:
            raise DomainError(DomainErrorCode.CONFLICT, "Cannot activate revoked membership")
        m.status = MembershipStatus.ACTIVE
        m.activated_at = utc_now()
        m.touch()
        self._session.add(m)
        await self._session.commit()
        await self._session.refresh(m)
        return m

    async def suspend(
        self, membership_id: UUID, *, actor_user_id: UUID | None = None
    ) -> Membership:
        m = await self._session.get(Membership, membership_id)
        if m is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Membership not found")
        before = {"status": m.status.value}
        m.status = MembershipStatus.SUSPENDED
        m.touch()
        self._session.add(m)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="security.membership.suspend",
            event_type="membership.suspended",
            resource_type="membership",
            resource_id=m.id,
            business_id=m.business_id,
            actor_user_id=actor_user_id,
            before=before,
            after={"status": m.status.value},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(m)
        return m

    async def revoke(
        self, membership_id: UUID, *, actor_user_id: UUID | None = None
    ) -> Membership:
        from app.core_platform.audit.service import AuditService
        from app.core_platform.events.service import EventService
        from app.models.audit import AuditOutcome

        m = await self._session.get(Membership, membership_id)
        if m is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Membership not found")
        before = {"status": m.status.value}
        m.status = MembershipStatus.REVOKED
        m.revoked_at = utc_now()
        m.touch()
        self._session.add(m)
        await self._session.flush()
        await AuditService(self._session).record(
            action="security.membership.revoke",
            resource_type="membership",
            resource_id=m.id,
            business_id=m.business_id,
            actor_user_id=actor_user_id,
            outcome=AuditOutcome.SUCCESS,
            before=before,
            after={"status": m.status.value},
            commit=False,
        )
        await EventService(self._session).emit(
            event_type="membership.revoked",
            aggregate_type="membership",
            aggregate_id=m.id,
            business_id=m.business_id,
            actor_user_id=actor_user_id,
            payload={"membership_id": str(m.id), "user_id": str(m.user_id)},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(m)
        return m

    async def list_for_business(self, business_id: UUID) -> list[Membership]:
        result = await self._session.exec(
            select(Membership).where(
                Membership.business_id == business_id,
                Membership.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        return list(result.all())


class RoleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_system_permissions(self) -> None:
        for code, description in SYSTEM_PERMISSIONS:
            existing = (await self._session.exec(
                select(Permission).where(Permission.code == code)
            )).first()
            if existing is None:
                self._session.add(
                    Permission(id=uuid4(), code=code, description=description)
                )
        await self._session.commit()

    async def create_role(
        self, business_id: UUID, name: str, *, is_system: bool = False
    ) -> Role:
        role = Role(id=uuid4(), business_id=business_id, name=name, is_system=is_system)
        self._session.add(role)
        await self._session.commit()
        await self._session.refresh(role)
        return role

    async def attach_permission(self, role_id: UUID, permission_code: str) -> None:
        perm = (await self._session.exec(
            select(Permission).where(Permission.code == permission_code)
        )).first()
        if perm is None:
            raise DomainError(DomainErrorCode.NOT_FOUND, f"Permission {permission_code}")
        existing = await self._session.get(RolePermission, (role_id, perm.id))
        if existing:
            return
        self._session.add(RolePermission(role_id=role_id, permission_id=perm.id))
        await self._session.commit()

    async def assign_role(
        self,
        membership_id: UUID,
        role_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        business_id: UUID | None = None,
    ) -> None:
        existing = await self._session.get(MembershipRole, (membership_id, role_id))
        if existing:
            return
        self._session.add(MembershipRole(membership_id=membership_id, role_id=role_id))
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="security.role.assign",
            event_type="role.assigned",
            resource_type="membership",
            resource_id=membership_id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            after={"role_id": str(role_id)},
            commit=False,
        )
        await self._session.commit()

    async def bootstrap_owner(
        self, business_id: UUID, membership_id: UUID
    ) -> Role:
        """Create system Owner role with all Core permissions for a new business."""
        await self.ensure_system_permissions()
        role = Role(
            id=uuid4(),
            business_id=business_id,
            name="Owner",
            is_system=True,
        )
        self._session.add(role)
        await self._session.flush()
        perms = (
            await self._session.exec(select(Permission))
        ).all()
        for perm in perms:
            self._session.add(
                RolePermission(role_id=role.id, permission_id=perm.id)
            )
        self._session.add(
            MembershipRole(membership_id=membership_id, role_id=role.id)
        )
        await self._session.commit()
        await self._session.refresh(role)
        return role


class AuthorizationService:
    """Resolve effective permissions and assert access."""

    def __init__(self, session: AsyncSession | None) -> None:
        self._session = session

    async def effective_permissions(self, membership_id: UUID) -> frozenset[str]:
        assert self._session is not None
        role_ids = (
            await self._session.exec(
                select(MembershipRole.role_id).where(
                    MembershipRole.membership_id == membership_id
                )
            )
        ).all()
        if not role_ids:
            return frozenset()
        perm_ids = (
            await self._session.exec(
                select(RolePermission.permission_id).where(
                    RolePermission.role_id.in_(role_ids)
                )
            )
        ).all()
        if not perm_ids:
            return frozenset()
        codes = (
            await self._session.exec(
                select(Permission.code).where(Permission.id.in_(perm_ids))
            )
        ).all()
        return frozenset(codes)

    @staticmethod
    def assert_scope(
        scopes: list[ScopeAssignment],
        *,
        branch_id: UUID | None,
        location_id: UUID | None,
    ) -> None:
        """Enforce branch/location allowlists from ScopeAssignment rows.

        Semantics (frozen contract — see CORE_CONTRACTS §Scope):

        - **Empty scope list (no ScopeAssignment rows)** → **full business access**.
          Intended for single-branch SMEs and HQ/Owner staff who operate across
          all branches. Membership + permissions already authorize the business;
          empty does **not** mean "denied".
        - **Non-empty scope list** → explicit **allowlist**. When branch scoping
          is enabled for a membership (at least one ScopeAssignment row), the
          requested ``branch_id`` / ``location_id`` must be in the allowed set
          or Core raises FORBIDDEN.
        - **No branch_id/location_id on the request** → business-level only;
          no branch/location check is applied.
        - Future policy option: businesses that enable mandatory branch scoping
          could treat empty as denied for non-Owner roles — not current behavior.
        - Domains must not re-implement this; they receive TenantContext from Core.
        """
        if not scopes:
            return
        allowed_branches = {s.branch_id for s in scopes if s.branch_id is not None}
        allowed_locations = {s.location_id for s in scopes if s.location_id is not None}
        if branch_id is not None and allowed_branches and branch_id not in allowed_branches:
            raise DomainError(DomainErrorCode.FORBIDDEN, "Branch out of scope")
        if (
            location_id is not None
            and allowed_locations
            and location_id not in allowed_locations
        ):
            raise DomainError(DomainErrorCode.FORBIDDEN, "Location out of scope")

    async def build_tenant_context(
        self,
        *,
        user_id: UUID,
        business_id: UUID,
        request_id: UUID,
        branch_id: UUID | None = None,
        location_id: UUID | None = None,
    ) -> TenantContext:
        assert self._session is not None
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
        scopes = list(
            (
                await self._session.exec(
                    select(ScopeAssignment).where(
                        ScopeAssignment.membership_id == m.id,
                        ScopeAssignment.deleted_at.is_(None),  # type: ignore[attr-defined]
                    )
                )
            ).all()
        )
        self.assert_scope(scopes, branch_id=branch_id, location_id=location_id)
        perms = await self.effective_permissions(m.id)
        return TenantContext(
            business_id=business_id,
            actor_user_id=user_id,
            membership_id=m.id,
            request_id=request_id,
            permissions=perms,
            branch_id=branch_id,
            location_id=location_id,
        )

    def require_permission(self, ctx: TenantContext, code: str) -> None:
        if code not in ctx.permissions:
            raise DomainError(
                DomainErrorCode.FORBIDDEN, f"Missing permission: {code}"
            )


    async def assign_scope(
        self,
        *,
        membership_id: UUID,
        branch_id: UUID | None,
        location_id: UUID | None,
        actor_user_id: UUID | None,
        business_id: UUID,
    ) -> ScopeAssignment:
        m = await self._session.get(Membership, membership_id)
        if m is None or m.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Membership not found")
        row = ScopeAssignment(
            id=uuid4(),
            membership_id=membership_id,
            branch_id=branch_id,
            location_id=location_id,
        )
        self._session.add(row)
        await self._session.flush()
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="security.scope.assign",
            event_type="scope.assigned",
            resource_type="scope_assignment",
            resource_id=row.id,
            business_id=business_id,
            actor_user_id=actor_user_id,
            after={
                "membership_id": str(membership_id),
                "branch_id": str(branch_id) if branch_id else None,
                "location_id": str(location_id) if location_id else None,
            },
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def list_scopes(
        self, *, membership_id: UUID, business_id: UUID
    ) -> list[ScopeAssignment]:
        m = await self._session.get(Membership, membership_id)
        if m is None or m.business_id != business_id:
            raise DomainError(DomainErrorCode.NOT_FOUND, "Membership not found")
        result = await self._session.exec(
            select(ScopeAssignment).where(
                ScopeAssignment.membership_id == membership_id,
                ScopeAssignment.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
        return list(result.all())
