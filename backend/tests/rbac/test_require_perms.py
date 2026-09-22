"""P0: permission denial contract."""

from uuid import uuid4

import pytest

from app.core_platform.security.service import AuthorizationService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext


def _ctx(perms: set[str]) -> TenantContext:
    return TenantContext(
        business_id=uuid4(),
        actor_user_id=uuid4(),
        membership_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset(perms),
    )


def test_owner_like_permissions_allow_catalog():
    svc = AuthorizationService(session=None)
    ctx = _ctx({"catalog.product.create", "catalog.product.read"})
    svc.require_permission(ctx, "catalog.product.create")
    svc.require_permission(ctx, "catalog.product.read")


def test_member_without_security_denied():
    svc = AuthorizationService(session=None)
    ctx = _ctx({"catalog.product.read"})
    with pytest.raises(DomainError) as ei:
        svc.require_permission(ctx, "security.membership.revoke")
    assert ei.value.code == DomainErrorCode.FORBIDDEN
    assert "Missing permission" in ei.value.message


def test_audit_read_required():
    svc = AuthorizationService(session=None)
    ctx = _ctx(set())
    with pytest.raises(DomainError):
        svc.require_permission(ctx, "audit.read")
