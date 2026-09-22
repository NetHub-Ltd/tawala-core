"""IDOR party access — full coverage in tests/postgres (real PostgreSQL)."""

from __future__ import annotations

from app.core_platform.shared.types import DomainErrorCode


def test_not_found_and_forbidden_codes_stable():
    assert DomainErrorCode.NOT_FOUND == "not_found"
    assert DomainErrorCode.FORBIDDEN == "forbidden"
