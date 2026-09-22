"""Password hashing unit tests."""

from app.core_platform.identity.password import hash_password, hash_token, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", h)
    assert not verify_password("wrong-password", h)


def test_hash_token_stable():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
