# Domain Contracts — Core-owned primitives

**Branch:** `core/v2` only  
**Gate:** T6 / M16 — Core Domain Contract Layer  
**Status:** Binding for Inventory, Sales, Purchasing, Accounting, CRM, Reporting  
**Related:** `CORE_CONTRACTS.md` (cross-cutting), `TAWALA_CORE_DESIGN.md`, `MERGE_POLICY.md`

This document defines what **future operational domains** may assume about Core-owned entities.  
Domains **query and reference** these identities. They **must not** own parallel copies of Business, Party, or Product identity.

Cross-cutting rules (TenantContext, RBAC, entitlements, audit, outbox, RLS) remain in `CORE_CONTRACTS.md`.

---

## 0. Ownership matrix

| Concept | Owner | Downstream domains may |
|---------|-------|------------------------|
| Business / Branch / Location | Core (Organization) | Reference IDs; never create alternate tenant roots |
| Party + PartyBusinessLink | Core (Parties) | Reference `party_id` / link; extend via own tables keyed to party |
| Product / Service / Category | Core (Catalog) | Reference `product_id`; **never** store stock on Product |
| Membership / Role / Permission | Core (Security) | Consume via TenantContext; no shadow ACL |
| Capability / Entitlement | Core (Entitlements) | Gate modules via `EntitlementService` / `require_capability` |
| Stock quantity / movements | **Inventory domain (future)** | Own stock tables; FK to Product + Location |
| Sales documents / lines | **Sales domain (future)** | FK to Product, Party, Branch |
| Purchases / suppliers ops | **Purchasing domain (future)** | FK to Party (supplier), Product |
| Journal / ledger | **Accounting domain (future)** | FK to Business; optional Party |

---

## 1. Organization contract

### Entities

| Entity | Identity | Tenant key | Notes |
|--------|----------|------------|-------|
| `Business` | `id` (UUID) | *is* the tenant root | Status: active / suspended / closed |
| `Branch` | `id` | `business_id` | Operational unit under Business |
| `Location` | `id` | `business_id` + `branch_id` | Shop, warehouse, etc. |

### Hierarchy

```text
Business 1──* Branch 1──* Location
```

### Rules for domains

1. Every operational row in a domain table **must** carry `business_id` matching the TenantContext business.
2. When a domain action is location-scoped, persist `location_id` (and usually `branch_id`) and respect Core scope assignments.
3. Do not invent a second “store” or “outlet” entity that duplicates Branch/Location.
4. Soft-deleted Organization rows (`deleted_at IS NOT NULL`) must not be used as new FK targets.

### Authoritative code

- Models: `backend/app/models/organization.py`
- Service: `backend/app/core_platform/organization/service.py`
- Routes: `backend/app/api/routes/organization.py`

---

## 2. Party contract

### Entities

| Entity | Identity | Tenant binding |
|--------|----------|----------------|
| `Party` | `id` (UUID) | Platform-level person/org identity |
| `PartyBusinessLink` | `id` | `business_id` + `party_id` + `relationship` |

### Relationships

`PartyRelationship`: customer | supplier | employee | member | other  
`LinkStatus`: active | inactive

A Party may link to many Businesses. A Business sees a Party **only** through an active link (enforced in Core read paths).

### Rules for domains

1. CRM, sales, and purchasing **reference** `party_id` (and optionally the link id). They do not re-create party name/email as system of record.
2. “Customer of business B” means: active `PartyBusinessLink` with `relationship=customer` for that business.
3. Domains may store **profile extensions** (e.g. credit limit) in domain tables keyed by `party_id` + `business_id`, not by mutating Core Party without a Core command.
4. Cross-tenant party access is forbidden; Core get-by-id paths check the link.

### Authoritative code

- Models: `backend/app/models/parties.py`
- Service: `backend/app/core_platform/parties/service.py`
- Routes: `backend/app/api/routes/parties.py`

---

## 3. Catalog contract

### Entities

| Entity | Identity | Tenant key | Forbidden fields |
|--------|----------|------------|------------------|
| `Category` | `id` | `business_id` | stock, quantity |
| `Product` | `id` | `business_id` | stock, quantity, on_hand, reserved |
| `Service` | `id` | `business_id` | duration-as-inventory, stock |

`CatalogStatus`: active | archived

### Hard rule — Catalog ≠ Inventory

```text
Product  = identity + commercial attributes (name, sku, unit, category)
Stock    = quantity at a Location (Inventory domain — not Core Catalog)
```

Any future Inventory table must FK to `products.id` and typically `locations.id`.  
Core Catalog schema and tests must reject quantity/stock columns on Product.

### Rules for domains

1. Sales lines, purchase lines, and stock movements reference `product_id` (or `service_id`).
2. Price may live in Catalog later or in a Pricing domain; quantity never lives on Product.
3. Creating catalog items requires RBAC (`catalog.*.create`) **and** entitlement `module.catalog` (T5).

### Authoritative code

- Models: `backend/app/models/catalog.py`
- Service: `backend/app/core_platform/catalog/service.py`
- Routes: `backend/app/api/routes/catalog.py`

---

## 4. How domains call Core

### Required chain (from CORE_CONTRACTS)

```text
Authenticate → TenantContext → RBAC → Entitlement → Scope → Domain op → Audit/Outbox
```

### Integration patterns

| Need | Pattern |
|------|---------|
| Act as user in a business | Obtain `TenantContext` via Core deps / AuthorizationService |
| Read product identity | Core Catalog service or HTTP API with permissions |
| Attach sale to customer | Persist `party_id` after verifying link via Parties service |
| Check plan feature | `EntitlementService.require(business_id, "module.…")` |
| Emit integration event | Use Core `record_activity` / `EventService.emit` in same UoW when mutating Core |

### Forbidden

- Direct SQL against Core tables from product services without going through Core APIs/services on this architecture branch.
- Copying Business/Product rows into domain tables as a new source of truth.
- Bypassing TenantContext with a client-supplied `business_id` alone.

---

## 5. Document primitives (shared vocabulary)

| Term | Meaning |
|------|---------|
| **Tenant root** | `Business.id` |
| **Actor** | `User.id` via membership |
| **Scope** | Optional branch/location constraint on membership |
| **Capability** | Product feature/limit code (`module.*`, `limit.*`) |
| **Permission** | RBAC action code (`catalog.product.create`) |
| **Party** | Real-world counterparty identity |
| **Catalog item** | Product or Service identity (not stock) |

---

## 6. Exit criteria (T6)

- [x] This document exists and is referenced from CORE_CONTRACTS
- [x] Ownership matrix covers Org, Party, Catalog vs future domains
- [x] Catalog schema test asserts no stock/quantity fields on Product
- [x] No operational Inventory/Sales domain tables introduced in this gate

---

## 7. Evolution

Later domain milestones (Inventory, Sales, …) **extend** this document with domain-specific sections; they must not contradict ownership rules above without an explicit contracts revision on `core/v2`.

## 8. Inventory contract (T7 / M17)

Inventory is the **sole owner of stock state**.

| Entity | Role |
|--------|------|
| `StockLevel` | Authoritative on-hand (and reserved) per product × location × business |
| `StockMovement` | Auditable history of every mutation |

### Negative stock policy

`quantity_on_hand` **must not** go below zero. Issue, transfer-out, and adjust targets that would undershoot raise `VALIDATION_FAILED`. Enforced in domain logic and DB check constraint.

### Mutation primitives

- `receive` — stock-in
- `issue` — stock-out
- `adjust` — set absolute on-hand (count); creates adjust movement
- `transfer` — atomic `transfer_out` + `transfer_in` with shared `transfer_group_id`

All mutations write a movement, update the level in the **same transaction**, emit audit/event via `record_activity`, and support command idempotency keys.

### Authoritative code

- Models: `backend/app/models/inventory.py`
- Service: `backend/app/core_platform/inventory/service.py`
- Routes: `backend/app/api/routes/inventory.py`

## 9. Accounting contract (T10 / M20)

Accounting is the **sole owner of financial truth**.

| Entity | Role |
|--------|------|
| `Account` | Business chart of accounts |
| `JournalEntry` / `JournalLine` | Balanced double-entry postings |
| `PaymentAllocation` | Link payment journals to invoices/POs |
| `FinancialEntry` | Domain adapter row (Sales/Purchasing) linked to `journal_entry_id` |

### Rules
- Journals must balance (debits = credits) or post is rejected.
- Reversals create compensating journals; originals are marked `reversed` (never deleted).
- Sales/Purchasing call `AccountingService.post_entry` only — they do not write journals directly.
- Tax hook: optional `tax_code` / `tax_amount` on domain posts (Tax Payable account).

## 10. CRM contract (T11)

CRM organizes **customer intelligence** on top of Party identity.

| Entity | Role |
|--------|------|
| `CustomerProfile` | Business-scoped credit, segment, tags (not identity) |
| `CustomerNote` | Staff notes |
| `CustomerActivity` | CRM activity history |

### Rules
- Identity remains `Party` + `PartyBusinessLink` (customer).
- Purchase history is **queried from Sales** finalized invoices — not copied into CRM tables.
- **Credit status authority:** `CustomerProfile.credit_status` / `credit_limit` (CRM). Accounting may inform UI later; CRM does not post journals.
- CRM never mutates Sales documents or Accounting journals.

## 11. Reporting contract (T12)

Reporting is a **read-only** consumer of authoritative domain data.

| Metric | Authoritative source | Calculation | Scope | Time |
|--------|---------------------|-------------|-------|------|
| sales_by_day | `sales_documents` + `sales_lines` | Sum line_total on FINALIZED invoices | business, optional branch | `finalized_at` UTC day |
| sales_by_product | same | Group by product_id | business, optional branch/day | finalized_at |
| sales_by_customer | same | Group by party_id | business, optional day | finalized_at |
| inventory_on_hand | `stock_levels` | Current quantity | business, optional location | point-in-time |
| purchasing_open_pos | `purchase_orders` | Status in draft/confirmed/partial | business | current |
| grn_finalized_count | `goods_receipts` | FINALIZED count | business, optional day | created_at |
| payments_collected | `sales_payments` | Sum amount | business, optional day | received_at |
| journal_posted_count | `journal_entries` | POSTED count | business | current |

### Rules
- Reporting **must not** write Sales, Inventory, Accounting, Purchasing, or CRM tables.
- Metrics never invent financial or stock truth; they only project source rows.
- Tenant filter is always `business_id` from the caller context.
