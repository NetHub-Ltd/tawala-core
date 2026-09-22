"""Identity schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas.identity import UserLogin, UserRegister


def test_register_requires_email_or_phone():
    with pytest.raises(ValidationError):
        UserRegister(password="password12")


def test_register_email_ok():
    u = UserRegister(email="a@example.com", password="password12")
    assert u.email is not None


def test_login_requires_identifier():
    with pytest.raises(ValidationError):
        UserLogin(password="x")
