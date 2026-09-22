"""Membership gate — behavior proven under tests/postgres (real PostgreSQL).

This module keeps a lightweight contract check that does not use FakeSession.
Full isolation evidence lives in tests/postgres/test_tenant_isolation_http.py.
"""

from __future__ import annotations

from app.core_platform.shared.types import DomainErrorCode


def test_forbidden_code_stable():
    assert DomainErrorCode.FORBIDDEN == "forbidden"
