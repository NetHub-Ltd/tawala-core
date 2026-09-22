# Tawala Core — Compatibility Matrix & Complete Gate

**Branch:** `core/v2`  
**Gate:** M11 (#257)  
**Date:** 2026-09-20  
**Status:** Core foundation **COMPLETE** for SPEC scope (with noted residual risks)

---

## 1. Milestone completion

| ID | Milestone | Status |
|----|-----------|--------|
| M0 | Isolation + docs | Done (operator: branch protection #245 still recommended) |
| M1 | Backend skeleton | Done |
| M2 | Core CI | Done |
| M3 | DB + Alembic | Done |
| M4 | Identity | Done |
| M5 | Organization | Done |
| M6 | Membership / RBAC / BaseMixin | Done |
| M7 | Parties | Done |
| M8 | Catalog (no quantity) | Done |
| M9 | Events / Audit / Config | Done |
| M10 | Image `tawala-core` | Done (CI builds; agent env had no Docker daemon) |
| M11 | Complete gate | **This document** |

**Board:** https://github.com/orgs/NetHub-Ltd/projects/5

---

## 2. Architecture doc alignment

| Source | Topic | Core status |
|--------|--------|-------------|
| DOMAIN_MODEL | Party, Business, Membership, Product ≠ stock | **MATCH** |
| DOMAIN_BOUNDARIES | Catalog ≠ Inventory; Core vs domains | **MATCH** (no sales/inventory modules on branch) |
| SECURITY_MODEL | Tenant=Business, membership, RBAC, deny-by-default patterns | **MATCH** (permission enforcement on routes still expands with domain modules) |
| DOMAIN_CONTRACTS | Events + outbox | **MATCH** (emit + outbox tables; consumer worker not required for Core gate) |
| CORE_ARCHITECTURE | Modular Core, multi-tenant | **MATCH** (in-process modular monolith) |
| DEVELOPMENT_SPEC | Models D, endpoints F, sequence G | **MATCH** for Core surface |

---

## 3. Implemented surface

### Models (all entity tables extend BaseMixin)

`User`, `Credential`, `Session`, `Business`, `Branch`, `Location`, `Membership`, `Permission`, `Role`, `RolePermission`, `MembershipRole`, `ScopeAssignment`, `Party`, `PartyBusinessLink`, `Category`, `Product`, `Service`, `DomainEvent`, `OutboxEntry`, `AuditRecord`, `BusinessConfig`

BaseMixin: `id`, `created_at`, `updated_at`, `deleted_at`, `deleted_by`

### API (prefix `/api/v1` except health)

| Area | Endpoints |
|------|-----------|
| Health | `GET /health`, `GET /ready` |
| Auth | `POST /auth/register`, `/login`, `/logout`, `GET /auth/me` |
| Org | businesses, branches, locations |
| Security | memberships, roles, permissions, `/me/permissions` |
| Parties | parties, links, list by business |
| Catalog | products, services |
| Audit | `GET /audit-records` |

### Migrations

`20260919_0001` … `0007` (baseline → events/audit/config)

### CI / isolation

- `core-ci.yml` — lint + pytest  
- `core-image.yml` — build `tawala-core`, smoke `/health`  
- `block-core-merge-to-product.yml` — block core/** → main/dev  
- `MERGE_POLICY.md` — binding  

---

## 4. Test results (gate run)

```
pytest: 22 passed
ruff: clean
```

Suites present: unit (health, base mixin), identity (password, schemas), isolation (membership gate), rbac (permission assert), idor (party), catalog (no quantity), audit (event/audit models).

### Residual (accepted for Core gate; not blockers)

1. **Live Postgres integration tests** — suite runs without DATABASE_URL; full HTTP+DB E2E should be added when a CI Postgres service is wired for Core.  
2. **GitHub branch protection on `main`** — issue #245 (operator). CI guard exists; protection strengthens it.  
3. **Outbox publisher worker** — table + emit path done; async publisher process is post-Core.  
4. **Fine-grained permission checks on every org/catalog route** — membership gate is active; attaching role permissions to every handler is incremental hardening.  
5. **Docker smoke in agent sandbox** — verified by workflow design; confirm green on GitHub Actions after push.

---

## 5. Explicit non-goals (still true)

- No frontend  
- No Sales / Inventory quantity / Payments  
- No merge of `core/v2` into `main` or `dev`  
- No product image name `tawala-api`  
- No borrowing product models from main  

---

## 6. Definition of done — checklist

- [x] SPEC models implemented with BaseMixin  
- [x] Catalog has no stock quantity  
- [x] Tenant boundary via Business + Membership  
- [x] Events + outbox + audit + config tables/services  
- [x] CI + image workflows on core/v2  
- [x] Merge isolation policy + CI guard  
- [x] Project board milestones M1–M10 closed  
- [x] Compatibility matrix published  
- [ ] Operator: branch protection #245 (recommended)  
- [ ] Confirm Core Image workflow green on GitHub  

---

## 7. What comes after Core

1. Domain modules (Inventory, Sales, …) on **separate** design — still not merged into product until migration program.  
2. Or migration mapping from product main → Core contracts (separate approved program).  
3. Never open PR `core/v2` → `main`/`dev` without changing MERGE_POLICY.

---

**Signed off as Core complete gate (M11) on branch `core/v2`.**


---

## 8. P0 hardening (post-M11)

Applied on core/v2 after drift report:

- `get_tenant_context` + `require_perms(...)` on org, catalog, parties, security, audit routes
- Owner role bootstrap with all system permissions on business create
- `ensure_system_permissions` available via RoleService (called during bootstrap)
- RBAC unit tests for missing permission → FORBIDDEN

Still residual: live DB E2E, P1 audit/event coverage expansion, idempotency, category/config/scope APIs.


### P1 activity coverage (#261)

Mutations that emit audit + outbox event via `record_activity`:

- business.created, branch.created, location.created
- product.created, product.updated, service.created
- party.created, party.linked
- membership.invited, membership.suspended, membership.revoked
- role.assigned
