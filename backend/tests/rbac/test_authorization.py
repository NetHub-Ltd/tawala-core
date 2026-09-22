"""AuthorizationService permission gate."""

from uuid import uuid4

import pytest

from app.core_platform.security.service import AuthorizationService
from app.core_platform.shared.types import DomainError, DomainErrorCode, TenantContext


def test_require_permission_denies_missing():
    svc = AuthorizationService(session=None)  # type: ignore[arg-type]
    ctx = TenantContext(
        business_id=uuid4(),
        actor_user_id=uuid4(),
        membership_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset({"catalog.product.read"}),
    )
    with pytest.raises(DomainError) as ei:
        svc.require_permission(ctx, "security.role.manage")
    assert ei.value.code == DomainErrorCode.FORBIDDEN


def test_require_permission_allows_present():
    svc = AuthorizationService(session=None)  # type: ignore[arg-type]
    ctx = TenantContext(
        business_id=uuid4(),
        actor_user_id=uuid4(),
        membership_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset({"security.role.manage"}),
    )
    svc.require_permission(ctx, "security.role.manage")
