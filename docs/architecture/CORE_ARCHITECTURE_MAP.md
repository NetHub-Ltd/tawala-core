# Tawala Core — Architecture Map (T13 / M23 Certification)

**Branch:** `core/v2` only · **Image:** `tawala-core` · **Updated:** 2026-09-22

This document is the certification evidence map for cross-domain integrity.
It does not introduce new domain ownership.

## 1. Source of truth by concern

| Concern | Authoritative owner | Not authoritative |
|---------|---------------------|-------------------|
| Tenant / business | Organization (`Business`, RLS GUC) | Clients, reporting |
| Identity of people/orgs | `Party` + `PartyBusinessLink` | CRM profile |
| What is sold | Catalog (`Product` / `Service`) | Inventory |
| Stock quantity / location | Inventory (`StockLevel`, `StockMovement`) | Sales lines, reporting |
| Sales commercial docs | Sales (`SalesDocument`, lines, payments) | CRM, reporting |
| Procurement docs | Purchasing (PO, GRN) | Inventory (only stock effects) |
| Financial truth | Accounting (`JournalEntry` / lines, COA) | Sales payment rows alone |
| Customer intelligence | CRM (`CustomerProfile`, notes) — on Party | Transaction totals stored in CRM |
| Analytics projections | Reporting (read-only queries) | Any write path |

## 2. Domain owner → mutation path → transaction boundary

```text
Caller + TenantContext + RBAC + module entitlement
    ↓
Domain service (Sales | Inventory | …)
    ↓
Single AsyncSession unit of work
    ↓
Optional: inventory effect / accounting post_entry / outbox emit
    ↓
commit
    ↓
Audit / DomainEvent / OutboxEntry (as implemented per service)
```

| Domain | Primary mutation API | Side effects inside same UoW |
|--------|----------------------|------------------------------|
| Inventory | receive / issue / transfer / adjust | StockMovement ledger |
| Sales | create_document, finalize_invoice, record_payment | Issue stock; accounting posts |
| Purchasing | PO + finalize GRN | Receive stock; supplier liability |
| Accounting | post_journal, reverse_journal, post_entry | Balanced journal lines |
| CRM | profile / notes | Activity log only — no sales/finance writes |
| Reporting | **none** | Read-only |

## 3. Audit / events / consumers

```text
Mutation
  → record_activity / DomainEvent (where wired)
  → OutboxEntry PENDING
  → OutboxPublisher claim (FOR UPDATE SKIP LOCKED) → PUBLISHED | FAILED+retry

Consumers (read):
  CRM purchase_history ← Sales finalized invoices
  Reporting metrics    ← Sales, Inventory, Purchasing, Accounting tables
```

## 4. Isolation contracts

- **Tenant:** `business_id` on domain rows + Postgres RLS GUCs (`app.current_business_id`, `app.rls_bypass`)
- **Branch scope:** enforced where ScopeAssignment / branch filters apply (HTTP scope tests)
- **Capability:** `module.*` entitlements (e.g. `module.reporting`) + permission codes

## 5. Explicit non-goals / remaining unknowns

- Product POS (`main`/`dev`) is **not** certified by this map; Core remains isolated.
- Full HTTP E2E for every permission matrix cell is not exhaustively enumerated here; certification tests cover the critical chain + outbox + stock guard.
- Real message-bus delivery beyond in-process outbox sink is out of scope for Core foundation.

## 6. Certification test entrypoint

PostgreSQL:

```text
tests/certification/test_cross_domain_chain.py
```

Covers: tenant isolation, inventory authority, sales finalize + payment, accounting journals present, CRM on Party, reporting projection, outbox publish, insufficient-stock rejection.
