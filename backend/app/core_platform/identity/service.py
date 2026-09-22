"""IdentityService — register, authenticate, sessions (SPEC E.2 / M4)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core_platform.identity.password import hash_password, hash_token, verify_password
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.base import utc_now
from app.models.identity import Credential, CredentialType, Session, User, UserStatus
from app.schemas.identity import UserLogin, UserRegister

SESSION_TTL = timedelta(days=7)


class IdentityService:
    """Owns platform identity operations (not business membership)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, data: UserRegister) -> User:
        from app.core_platform.shared import idempotency as idem

        key = idem.require_key_format(getattr(data, "idempotency_key", None))
        if key:
            prior = await idem.lookup(self._session, scope="platform", key=key)
            if prior and prior.resource_id:
                user = await self._session.get(User, prior.resource_id)
                if user is not None:
                    return user
        if data.email:
            existing = (await self._session.exec(
                select(User).where(User.email == str(data.email).lower())
            )).first()
            if existing:
                raise DomainError(DomainErrorCode.CONFLICT, "Email already registered")
        if data.phone:
            existing = (await self._session.exec(select(User).where(User.phone == data.phone))).first()
            if existing:
                raise DomainError(DomainErrorCode.CONFLICT, "Phone already registered")

        user = User(
            id=uuid4(),
            email=str(data.email).lower() if data.email else None,
            phone=data.phone,
            display_name=data.display_name,
            status=UserStatus.ACTIVE,
        )
        self._session.add(user)
        await self._session.flush()
        cred = Credential(
            id=uuid4(),
            user_id=user.id,
            type=CredentialType.PASSWORD,
            secret_hash=hash_password(data.password),
        )
        self._session.add(cred)
        await self._session.flush()
        from app.core_platform.shared import idempotency as idem

        key = idem.require_key_format(getattr(data, "idempotency_key", None))
        if key:
            await idem.store(
                self._session,
                scope="platform",
                key=key,
                operation="auth.register",
                response_body={"id": str(user.id)},
                response_status=201,
                resource_id=user.id,
                commit=False,
            )
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="auth.register",
            event_type="auth.user.registered",
            resource_type="user",
            resource_id=user.id,
            business_id=None,
            actor_user_id=user.id,
            payload={"email": user.email, "phone": user.phone},
            after={"id": str(user.id), "status": user.status.value},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def login(
        self,
        data: UserLogin,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[User, Session, str]:
        user: User | None = None
        if data.email:
            user = (await self._session.exec(
                select(User).where(User.email == str(data.email).lower())
            )).first()
        elif data.phone:
            user = (await self._session.exec(select(User).where(User.phone == data.phone))).first()

        if user is None or user.status != UserStatus.ACTIVE:
            raise DomainError(DomainErrorCode.UNAUTHORIZED, "Invalid credentials")

        cred = (await self._session.exec(
            select(Credential).where(
                Credential.user_id == user.id,
                Credential.type == CredentialType.PASSWORD,
            )
        )).first()
        if cred is None or not verify_password(data.password, cred.secret_hash):
            raise DomainError(DomainErrorCode.UNAUTHORIZED, "Invalid credentials")

        raw_token = secrets_token()
        session = Session(
            id=uuid4(),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=utc_now() + SESSION_TTL,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(session)
        from app.core_platform.shared.activity import record_activity

        await record_activity(
            self._session,
            action="auth.login",
            event_type="auth.session.created",
            resource_type="session",
            resource_id=session.id,
            business_id=None,
            actor_user_id=user.id,
            payload={"user_agent": user_agent, "ip": ip},
            after={"user_id": str(user.id), "session_id": str(session.id)},
            commit=False,
        )
        await self._session.commit()
        await self._session.refresh(user)
        return user, session, raw_token

    async def logout(self, raw_token: str) -> None:
        token_h = hash_token(raw_token)
        session = (await self._session.exec(select(Session).where(Session.token_hash == token_h))).first()
        if session is None or session.revoked_at is not None:
            return
        session.revoked_at = utc_now()
        self._session.add(session)
        await self._session.commit()

    async def resolve_user(self, raw_token: str) -> User:
        token_h = hash_token(raw_token)
        session = (await self._session.exec(select(Session).where(Session.token_hash == token_h))).first()
        if session is None or session.revoked_at is not None:
            raise DomainError(DomainErrorCode.UNAUTHORIZED, "Invalid or revoked session")
        if session.expires_at < utc_now():
            raise DomainError(DomainErrorCode.UNAUTHORIZED, "Session expired")
        user = await self._session.get(User, session.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise DomainError(DomainErrorCode.UNAUTHORIZED, "User not available")
        return user


def secrets_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)
