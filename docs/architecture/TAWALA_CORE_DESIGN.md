# TAWALA CORE DESIGN

**Version:** 0.1.0-draft  
**Status:** Blueprint (proposal) — not yet accepted as final  
**Branch:** `core/v2`  
**Depends on:**  
- TAWALA_CORE_ARCHITECTURE  
- TAWALA_DOMAIN_MODEL  
- TAWALA_SECURITY_MODEL  
- TAWALA_DOMAIN_BOUNDARIES  
- TAWALA_DOMAIN_CONTRACTS  

**Purpose:** Define what Tawala Core **is**, how it is laid out, what data it owns, how entities relate, and what invariants it must enforce — so implementation can follow without inventing architecture in code.

**Non-purpose:** This document is not application source code. It does not implement FastAPI routes, SQLAlchemy models, or UI.

---

## 0. Binding constraints

| Constraint | Rule |
|------------|------|
| Isolation | `core/v2` is never merged into `main` or `dev` (see `MERGE_POLICY.md`) |
| No product borrow | No models, routes, CRUD, or frontend from the current product |
| No frontend | Core has no Web/Desktop/Mobile UI on this branch |
| Industry neutrality | Core must not contain `if industry == …` business logic |
| Tenant boundary | **Business** is the isolation boundary for business data |
| Catalog ≠ Inventory | Product identity has **no** stock quantity |
| Server decides | Authorization and tenancy are enforced in Core services, not clients |
| Deny by default | Missing membership, permission, or scope → deny |

---

## 1. What Core is

Tawala Core is the **platform foundation**: identity, membership, security, organization structure, generic business vocabulary, event and audit primitives, and configuration hooks.

Core answers:

- Who is acting?
- In which Business?
- What are they allowed to do (permission + scope)?
- What generic things exist (Party, Product identity, Location, Document lifecycle, Event envelope)?

Core does **not** answer:

- How is a sale completed?
- How is stock adjusted?
- How does M-PESA settle?
- How does accounting post journals?

Those belong to domain modules (Sales, Inventory, Payments, Accounting, …) that **consume Core contracts** and own their own data.

```text
                    TAWALA
                       |
              +--------+--------+
              |                 |
         TAWALA CORE      DOMAIN MODULES
              |                 |
     Identity / Security      Sales
     Organization             Inventory
     Parties                  CRM
     Catalog (identity)       Purchasing
     Events / Audit           Payments
     Configuration            Accounting
              |                 |
              +--------+--------+
                       |
                  API CONTRACTS
                       |
              +--------+--------+
              |        |        |
            Web    Desktop   Mobile
```

Clients are out of scope for this branch; APIs will be client-agnostic later.

---

## 2. Module layout (target package map)

Logical packages (implementation may use Python packages under a single backend app later; names are architectural):

```text
tawala_core/
├── identity/          # User identity, credentials, sessions (authn)
├── security/          # Membership, Role, Permission, Scope, authz decisions
├── organization/      # Business, Branch, Location
├── parties/           # Party + business relationships (Customer, Supplier, …)
├── catalog/           # Product / Service identity only (no stock quantity)
├── documents/         # Document lifecycle primitives (generic)
├── events/            # Domain event envelope, outbox interface
├── audit/             # Audit record append model
├── configuration/     # Business-scoped configuration keys
└── shared/            # Money, identifiers, time, errors, tenant context types
```

**Rules:**

- Domain modules (Sales, Inventory, …) **must not** live inside `tawala_core/`.
- Core packages **must not** import Sales/Inventory/Payments implementations.
- Shared kernel stays small: IDs, money representation, tenant context DTO, common errors, event envelope — not Sale or StockLevel.

---

## 3. Tenant and security model (Core)

### 3.1 Identity vs membership

```text
User (Identity)
    |
    +-- Membership --+--> Business
                     |
                     +--> Role(s) --> Permission(s)
                     |
                     +--> Scope (optional: Branch / Location)
```

- **User** = authenticated person (platform identity).
- **Membership** = authorized relationship of a User to a **Business**.
- No business data access without an **active** membership for that Business.
- Client-supplied `business_id` is a request, not proof of access.

### 3.2 Tenant context (required on protected operations)

Every protected Core (and later domain) operation carries:

```text
TenantContext
├── business_id          # tenant boundary
├── actor_user_id        # who is acting
├── membership_id        # verified membership used
├── branch_id?           # if scoped
├── location_id?         # if scoped
├── permissions          # effective permission set for this context
├── request_id           # correlation
└── occurred_at
```

Missing or invalid context → **deny**.

### 3.3 Authorization chain

```text
Authenticate → Resolve membership for Business → Load roles/permissions
  → Evaluate scope → Verify resource belongs to Business
  → Apply business rules (domain) → Operate → Audit (if required)
```

Deny by default at every step that fails.

### 3.4 Roles and permissions

- Permissions are capability strings, e.g. `organization.branch.create`, `catalog.product.update`, `security.membership.revoke`.
- Roles are named sets of permissions **within a Business** (or platform roles for platform admins — separate domain).
- No bypass path of the form `if is_owner: allow_all` without still recording permissions and audit for sensitive actions.

### 3.5 Scope

Scope restricts **where** a permission applies:

```text
Business (entire tenant)
  └── Branch
        └── Location
```

Cross-branch or cross-location access without scope → deny.

---

## 4. Core entity design (conceptual data model)

Entities below are **logical**. Physical tables, column types, and ORM come after acceptance. Relationships are mandatory design.

### 4.1 Identity

| Entity | Owns | Notes |
|--------|------|--------|
| **User** | Platform identity | Email/phone identifiers, status; not a Business |
| **Credential** | Auth secrets / factors | Never log; hash passwords; no plain text |
| **Session** | Authenticated session | Expiry, revoke; device optional later |

User **does not** own business data.

### 4.2 Security

| Entity | Owns | Notes |
|--------|------|--------|
| **Membership** | User ↔ Business link | Lifecycle: Invited → Active → Suspended → Revoked |
| **Role** | Named permission set in a Business | Business-scoped |
| **Permission** | Capability string | Catalog of permissions (seeded / versioned) |
| **RolePermission** | Role ↔ Permission | |
| **MembershipRole** | Membership ↔ Role | |
| **ScopeAssignment** | Optional Branch/Location limits | |

### 4.3 Organization

| Entity | Owns | Notes |
|--------|------|--------|
| **Business** | Tenant root | Isolation boundary; legal/display name; status |
| **Branch** | Operational unit under Business | |
| **Location** | Place under Branch (or Business) | Shop, warehouse, room, etc. |

```text
Business 1..* Branch 1..* Location
```

All operational data in domains later references `business_id` (and often `branch_id` / `location_id`).

### 4.4 Parties

| Entity | Owns | Notes |
|--------|------|--------|
| **Party** | Real-world person or organization identity | Shared kernel of “who” |
| **PartyBusinessLink** | Party in context of one Business | Discriminator: Customer, Supplier, Employee, Member, … |
| **CustomerProfile** (optional thin) | CRM-oriented attributes for a link | Does **not** duplicate Party identity |

```text
Party
  └── PartyBusinessLink (business_id, kind=CUSTOMER|SUPPLIER|…)
        └── optional profile / notes owned by CRM later
```

**Invariant:** One Party identity; multiple relationship kinds per Business allowed when needed; no separate “SalesCustomer” identity.

### 4.5 Catalog (identity only)

| Entity | Owns | Notes |
|--------|------|--------|
| **Product** | Sellable/stockable identity | Name, SKU, barcode, unit, tax class refs — **NO quantity** |
| **Service** | Deliverable non-stock identity | Or unified Offer with type discriminator |
| **Category** | Business-scoped taxonomy | |

**Invariant:** Stock quantity, reservations, and movements are **not** Core Catalog fields. Inventory domain owns those later.

### 4.6 Documents (primitives)

| Entity | Owns | Notes |
|--------|------|--------|
| **Document** | Generic business document header | type, status, business_id, numbers, timestamps |
| **DocumentLifecycle** | Allowed transitions per type | Enforced in Core or by domain that owns the type |

Statuses (example): `DRAFT → ISSUED → COMPLETED` or `CANCELLED`.  
Hard delete of historical documents is not the default.

Domains (Sales, Purchasing) specialize document types; Core provides shared lifecycle and numbering hooks.

### 4.7 Events

| Entity | Owns | Notes |
|--------|------|--------|
| **DomainEvent** (envelope) | Fact that something happened | Immutable once stored |
| **OutboxEntry** | Reliable publish record | Same transaction as state change when implemented |

Envelope fields (minimum):

```text
event_id
event_type
occurred_at
business_id
actor_user_id?
request_id?
aggregate_type
aggregate_id
version
payload (structured)
```

Events are **facts**, not commands. Corrections publish new events.

### 4.8 Audit

| Entity | Owns | Notes |
|--------|------|--------|
| **AuditRecord** | Who did what to which resource | Append-oriented; not modifiable by ordinary roles |

Fields (minimum): actor, business_id, action, resource_type, resource_id, outcome, before/after or diff, request_id, occurred_at, reason?

Audit ≠ application debug log.

### 4.9 Configuration

| Entity | Owns | Notes |
|--------|------|--------|
| **BusinessConfig** | Key/value (or typed) settings per Business | Currency, numbering patterns, feature toggles |

No industry-specific hardcoding in Core; domains may define keys they consume.

---

## 5. Relationship diagram (Core)

```text
                         User
                           |
                     Membership
                      /    |    \
                     /     |     \
              Business    Role   Scope → Branch → Location
                 |          |
                 |     Permission
                 |
        +--------+--------+----------------+
        |        |        |                |
     Branch   Party   Product/Service   Document*
        |        |        |                |
    Location  Link     Category      (lifecycle)
                 |
            (Customer /
             Supplier / …)

        DomainEvent / Outbox / AuditRecord
                 |
            (reference business_id + aggregates)
```

\* Document specialization is owned by domains; Core owns shared rules.

---

## 6. Database design principles

1. **Single PostgreSQL database is acceptable** for the modular monolith; logical ownership still applies.
2. **Every business-owned row** carries `business_id` (UUID) unless it is pure platform identity (User/Credential).
3. **No dual tenancy fields** (`tenant_id` + `organization_id`). One name: `business_id` (Business = tenant).
4. **UUIDs** for public identifiers; no sequential IDs as sole security boundary.
5. **Soft lifecycle** preferred for historical records (cancel/revoke/archive), not silent hard delete.
6. **Foreign keys** for integrity within Core; domains reference Core IDs, not Core private tables by unrestricted join from outside packages.
7. **Unique constraints** where business rules require (e.g. SKU per Business, one active membership pair User+Business).
8. **Indexes** on `(business_id, …)` for all tenant-scoped queries.
9. **Row-Level Security** is optional later; application enforcement is mandatory first. RLS may be added as defense in depth without changing the logical model.

### 6.1 Suggested Core tables (logical names)

```text
users
credentials
sessions

businesses
branches
locations

memberships
roles
permissions
role_permissions
membership_roles
scope_assignments

parties
party_business_links

products
services
categories

documents              # optional thin generic; or deferred until first domain needs it

domain_events          # or outbox-only until consumers exist
outbox_entries
audit_records

business_configs
```

Physical DDL is produced only after this design is accepted.

### 6.2 Explicit non-tables in Core

```text
sales, sale_items, payments, stock_levels, stock_movements,
purchase_orders, journal_entries, invoices (domain-owned types), …
```

---

## 7. Contracts Core owns vs exposes

### 7.1 Core-owned commands (examples)

```text
CreateBusiness
CreateBranch
CreateLocation
InviteMembership / ActivateMembership / SuspendMembership / RevokeMembership
AssignRole / RevokeRole
CreateParty / LinkPartyToBusiness
CreateProduct / UpdateProduct / ArchiveProduct
CreateService / UpdateService
RecordAudit
PublishDomainEvent (internal) / EnqueueOutbox
```

### 7.2 Core-owned queries (examples)

```text
GetBusiness
ListBranches
GetMembershipForUser
ListEffectivePermissions
GetParty
GetProduct
SearchProducts
```

### 7.3 Core events (examples)

```text
BusinessCreated
BranchCreated
MembershipActivated
MembershipRevoked
RoleAssigned
PartyLinked
ProductCreated
ProductUpdated
```

### 7.4 What Core does not own

```text
CreateSale, ReserveStock, CreatePayment, PostJournal, …
```

Those are domain contracts (see DOMAIN_CONTRACTS). Domains **query** Core for Product/Party/Branch identity and **must not** write Core tables except through Core commands.

---

## 8. Invariants (must hold; tests will encode these)

1. A User without active Membership in Business B cannot read or write B’s data.
2. Knowing a resource UUID does not grant access (IDOR denied).
3. Product has no stock quantity field in Core.
4. Party is the single identity; Customer is a relationship kind (or profile), not a second identity root.
5. Membership Revoked cannot be used to authorize operations.
6. Scope cannot escape its Business.
7. Audit records are append-only for non-platform-break-glass roles.
8. Domain events are immutable after write.
9. No Core module imports a domain package.
10. No industry-specific branch in Core business rules.

---

## 9. Test strategy for Core (acceptance-oriented)

| Suite | Proves |
|-------|--------|
| **Tenant isolation** | Cross-business read/write denied |
| **IDOR** | Random UUIDs for branch, product, party, membership denied |
| **Membership lifecycle** | Only Active can authorize; Revoked fails closed |
| **RBAC** | Missing permission denied; role grants work |
| **Scope** | Branch-scoped actor cannot access other branch resources |
| **Catalog boundary** | No quantity on Product; no stock mutation API in Core |
| **Import boundary** | Static/archunit-style: core packages do not import domain |
| **Audit** | Sensitive security operations produce AuditRecord |
| **Event envelope** | Required fields present; immutability |

Implementation language and harness are chosen at implementation phase; the suites above are mandatory for “Core complete.”

---

## 10. Definition of “Core design complete” (this document)

This design is **accepted** when:

- [ ] Stakeholders agree module map and entity list
- [ ] Tenant = Business and no dual tenancy fields agreed
- [ ] Party model agreed (or explicit interim + ADR)
- [ ] Catalog excludes stock quantity agreed
- [ ] Invariants 1–10 agreed
- [ ] Contract ownership (Core vs domains) agreed
- [ ] Milestone board references this document

**Core implementation complete** is a later gate (models + tests green), tracked in `V2_CORE_MILESTONES.md`.

---

## 11. Explicit non-goals (this blueprint phase)

- Frontend / BFF / Next.js
- Sales, Inventory, Payments, Accounting implementation
- M-PESA or any provider adapter
- Data migration from product DB
- Microservices split
- PostgreSQL RLS mandatory in first implementation
- Desktop offline security subsystem

---

## 12. Open questions (resolve before implementation)

1. **Party:** Full Party + link model in Core v1, or interim Customer/Supplier tables with ADR to migrate to Party?
2. **Product vs Service:** Two tables or one `offers` table with type?
3. **Document table in Core:** Include thin generic Document now, or introduce when Sales/Purchasing land?
4. **Platform admin:** Separate security domain for NetHub operators (no automatic access to Business data)?
5. **Permission seed:** Fixed enum vs DB-driven permission registry?

Recommended defaults if “defaults OK”:

1. Party + link in Core v1  
2. Separate Product and Service tables  
3. Defer generic Document table until first domain needs it  
4. Yes — platform admin is separate; no silent tenant access  
5. DB-driven permission registry with seeded system permissions  

---

## 13. Next steps after acceptance

1. Freeze this document as v1.0.0 (or revise with answers to §12).  
2. Fill `V2_CORE_MILESTONES.md` with phased implementation milestones and test gates.  
3. Implement Core packages + DDL + tests on `core/v2` only.  
4. Never merge to `main`/`dev`; migration program is a separate approved track.

---

## 14. Traceability

| Design section | Architecture source |
|----------------|---------------------|
| §1 What Core is | CORE_ARCHITECTURE §§1–3 |
| §3 Tenant/security | SECURITY_MODEL; DOMAIN_MODEL Identity/Membership |
| §4 Entities | DOMAIN_MODEL §§5–39 |
| §4.5 Catalog | DOMAIN_BOUNDARIES Catalog vs Inventory |
| §7 Contracts | DOMAIN_CONTRACTS |
| §8 Invariants | SECURITY_MODEL + BOUNDARIES ownership rule |

---

**Status:** DRAFT — awaiting review and answers to §12.

**End of TAWALA_CORE_DESIGN.md**
