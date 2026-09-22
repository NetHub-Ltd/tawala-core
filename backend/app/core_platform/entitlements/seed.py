"""Seed catalog of product capabilities (T5). Distinct namespace from RBAC codes."""

from __future__ import annotations

from app.models.entitlements import CapabilityKind

SYSTEM_CAPABILITIES: list[tuple[str, CapabilityKind, str]] = [
    ("module.catalog", CapabilityKind.MODULE, "Catalog (products/services/categories)"),
    ("module.inventory", CapabilityKind.MODULE, "Inventory / stock operations"),
    ("module.sales", CapabilityKind.MODULE, "Sales / POS operations"),
    ("module.purchasing", CapabilityKind.MODULE, "Purchasing"),
    ("module.accounting", CapabilityKind.MODULE, "Accounting"),
    ("module.crm", CapabilityKind.MODULE, "CRM / customer intelligence"),
    ("module.reporting", CapabilityKind.MODULE, "Reporting / read models"),
    ("limit.staff.max", CapabilityKind.LIMIT, "Maximum active staff memberships"),
    ("limit.branches.max", CapabilityKind.LIMIT, "Maximum branches"),
    ("limit.products.max", CapabilityKind.LIMIT, "Maximum catalog products"),
    ("flag.api_access", CapabilityKind.FLAG, "API access enabled"),
]
