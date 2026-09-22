"""Catalog must reject stock quantity fields (SPEC M8)."""

import pytest
from pydantic import ValidationError

from app.models.catalog import Product
from app.schemas.catalog import ProductCreate, ProductUpdate


def test_product_create_rejects_quantity():
    with pytest.raises(ValidationError):
        ProductCreate(name="Widget", quantity=10)


def test_product_create_rejects_stock():
    with pytest.raises(ValidationError):
        ProductCreate(name="Widget", stock=5)


def test_product_update_rejects_on_hand():
    with pytest.raises(ValidationError):
        ProductUpdate(on_hand=1)


def test_product_model_has_no_quantity_column():
    cols = set(Product.model_fields.keys())
    assert "quantity" not in cols
    assert "stock" not in cols
    assert "on_hand" not in cols
    assert "name" in cols
    assert "business_id" in cols


def test_product_create_ok():
    p = ProductCreate(name="Widget", sku="W-1", unit="ea")
    assert p.name == "Widget"
