"""Register/login emit durable audit activity (#293)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.identity.service import IdentityService
from app.models.audit import AuditRecord
from app.schemas.identity import UserLogin, UserRegister


@pytest.mark.asyncio
async def test_register_writes_audit(db_session):
    svc = IdentityService(db_session)
    email = f"u-{uuid4().hex[:10]}@example.com"
    user = await svc.register(
        UserRegister(email=email, password="SecurePass1!", display_name="Audit User")
    )
    rows = list(
        (
            await db_session.exec(
                select(AuditRecord).where(
                    AuditRecord.action == "auth.register",
                    AuditRecord.resource_id == user.id,
                )
            )
        ).all()
    )
    assert len(rows) >= 1
    assert rows[0].resource_type == "user"


@pytest.mark.asyncio
async def test_login_writes_audit(db_session):
    svc = IdentityService(db_session)
    email = f"l-{uuid4().hex[:10]}@example.com"
    await svc.register(
        UserRegister(email=email, password="SecurePass1!", display_name="Login User")
    )
    user, session, _token = await svc.login(UserLogin(email=email, password="SecurePass1!"))
    rows = list(
        (
            await db_session.exec(
                select(AuditRecord).where(
                    AuditRecord.action == "auth.login",
                    AuditRecord.resource_id == session.id,
                )
            )
        ).all()
    )
    assert len(rows) >= 1
    assert rows[0].resource_type == "session"
    assert rows[0].actor_user_id == user.id
