"""Idempotency key validation (#262)."""

import pytest

from app.core_platform.shared.idempotency import require_key_format
from app.core_platform.shared.types import DomainError
from app.schemas.catalog import ProductCreate
from app.schemas.identity import UserRegister


def test_require_key_none():
    assert require_key_format(None) is None
    assert require_key_format("  ") is None


def test_require_key_ok():
    assert require_key_format("abc-123") == "abc-123"


def test_require_key_too_long():
    with pytest.raises(DomainError):
        require_key_format("x" * 200)


def test_product_create_accepts_idempotency_key():
    p = ProductCreate(name="Widget", idempotency_key="create-1")
    assert p.idempotency_key == "create-1"


def test_register_accepts_idempotency_key():
    u = UserRegister(email="a@example.com", password="password12", idempotency_key="reg-1")
    assert u.idempotency_key == "reg-1"
