"""Category and config schema smoke tests (#263)."""

from uuid import uuid4

from app.schemas.catalog import CategoryCreate
from app.schemas.configuration import ConfigSet
from app.schemas.security import ScopeAssign


def test_category_create():
    c = CategoryCreate(name="Beverages")
    assert c.parent_id is None


def test_config_set():
    c = ConfigSet(key="locale", value={"currency": "KES"})
    assert c.value["currency"] == "KES"


def test_scope_assign():
    s = ScopeAssign(membership_id=uuid4(), branch_id=uuid4())
    assert s.location_id is None
