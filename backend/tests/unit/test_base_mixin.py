"""BaseMixin soft-delete behaviour."""

from uuid import uuid4

from app.models.organization import Business


def test_base_mixin_soft_delete():
    b = Business(name="Acme")
    assert b.id is not None
    assert b.deleted_at is None
    assert not b.is_deleted
    actor = uuid4()
    b.soft_delete(by_user_id=actor)
    assert b.is_deleted
    assert b.deleted_by == actor
    assert b.deleted_at is not None


def test_touch_updates_timestamp():
    b = Business(name="Acme")
    before = b.updated_at
    b.touch()
    assert b.updated_at >= before
