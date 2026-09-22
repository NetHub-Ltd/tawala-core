"""T6 — structural invariants for Core domain primitives."""

from __future__ import annotations

from app.models.catalog import Category, Product, Service
from app.models.organization import Branch, Business, Location
from app.models.parties import Party, PartyBusinessLink


def _column_names(model) -> set[str]:
    return set(model.model_fields.keys())


def test_product_has_no_stock_columns():
    cols = _column_names(Product)
    forbidden = {
        "quantity",
        "qty",
        "stock",
        "on_hand",
        "onhand",
        "reserved",
        "available",
        "reorder_level",
    }
    assert forbidden.isdisjoint(cols), f"Product must not declare stock fields: {cols & forbidden}"


def test_product_has_tenant_and_identity_fields():
    cols = _column_names(Product)
    for required in ("id", "business_id", "name", "status"):
        assert required in cols


def test_service_and_category_tenant_scoped():
    assert "business_id" in _column_names(Service)
    assert "business_id" in _column_names(Category)


def test_organization_hierarchy_fields():
    assert "business_id" in _column_names(Branch)
    assert "business_id" in _column_names(Location)
    assert "branch_id" in _column_names(Location)
    assert "name" in _column_names(Business)


def test_party_link_binds_tenant():
    cols = _column_names(PartyBusinessLink)
    for required in ("business_id", "party_id", "relationship", "status"):
        assert required in cols
    # Party itself is not tenant-rooted
    assert "business_id" not in _column_names(Party)
