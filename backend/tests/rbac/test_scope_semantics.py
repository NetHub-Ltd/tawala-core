"""M13: Scope semantics unit tests (AuthorizationService.assert_scope)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core_platform.security.service import AuthorizationService
from app.core_platform.shared.types import DomainError, DomainErrorCode
from app.models.security import ScopeAssignment


def _scope(*, branch_id=None, location_id=None) -> ScopeAssignment:
    return ScopeAssignment(
        id=uuid4(),
        membership_id=uuid4(),
        branch_id=branch_id,
        location_id=location_id,
    )


def test_empty_scope_unrestricted():
    AuthorizationService.assert_scope([], branch_id=uuid4(), location_id=uuid4())


def test_explicit_branch_allows_listed():
    bid = uuid4()
    AuthorizationService.assert_scope(
        [_scope(branch_id=bid)], branch_id=bid, location_id=None
    )


def test_explicit_branch_denies_other():
    with pytest.raises(DomainError) as ei:
        AuthorizationService.assert_scope(
            [_scope(branch_id=uuid4())], branch_id=uuid4(), location_id=None
        )
    assert ei.value.code == DomainErrorCode.FORBIDDEN
    assert "Branch" in ei.value.message


def test_explicit_location_denies_other():
    with pytest.raises(DomainError) as ei:
        AuthorizationService.assert_scope(
            [_scope(location_id=uuid4())], branch_id=None, location_id=uuid4()
        )
    assert ei.value.code == DomainErrorCode.FORBIDDEN
    assert "Location" in ei.value.message


def test_no_request_branch_skips_check_even_with_scopes():
    AuthorizationService.assert_scope(
        [_scope(branch_id=uuid4())], branch_id=None, location_id=None
    )


def test_null_only_scope_rows_do_not_restrict_branch():
    """Rows with only null branch_id do not build an allowlist."""
    AuthorizationService.assert_scope(
        [_scope(branch_id=None, location_id=None)],
        branch_id=uuid4(),
        location_id=None,
    )
