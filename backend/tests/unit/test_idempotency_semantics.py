"""Command idempotency vs event delivery (T4)."""

from uuid import uuid4

import pytest

from app.core_platform.shared import idempotency as idem
from app.core_platform.shared.types import DomainError, DomainErrorCode


def test_require_key_format_none():
    assert idem.require_key_format(None) is None
    assert idem.require_key_format("  ") is None


def test_require_key_format_too_long():
    with pytest.raises(DomainError) as ei:
        idem.require_key_format("x" * 129)
    assert ei.value.code == DomainErrorCode.VALIDATION_FAILED


def test_require_key_format_ok():
    assert idem.require_key_format("  abc-123  ") == "abc-123"


@pytest.mark.asyncio
async def test_store_lookup_roundtrip(db_session):
    key = f"k-{uuid4()}"
    scope = str(uuid4())
    row = await idem.store(
        db_session,
        scope=scope,
        key=key,
        operation="catalog.product.create",
        response_body={"id": "1"},
        response_status=201,
        resource_id=uuid4(),
        commit=True,
    )
    found = await idem.lookup(db_session, scope=scope, key=key)
    assert found is not None
    assert found.id == row.id
    # second store returns same row — no duplicate effect
    again = await idem.store(
        db_session,
        scope=scope,
        key=key,
        operation="catalog.product.create",
        response_body={"id": "2"},
        response_status=201,
        commit=True,
    )
    assert again.id == row.id
    assert again.response_body.get("id") == "1"
