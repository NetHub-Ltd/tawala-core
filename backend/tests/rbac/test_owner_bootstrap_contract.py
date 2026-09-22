"""Owner bootstrap attaches all system permission codes conceptually."""

from app.core_platform.security.permissions_seed import SYSTEM_PERMISSIONS


def test_system_permissions_non_empty():
    codes = [c for c, _ in SYSTEM_PERMISSIONS]
    assert "catalog.product.create" in codes
    assert "security.membership.revoke" in codes
    assert "audit.read" in codes
    assert len(codes) >= 15
