# TAWALA CORE DEVELOPMENT SPECIFICATION

**Version:** 0.1.0-draft  
**Status:** Pre-implementation blueprint — **no application code until this document is accepted**  
**Branch:** `core/v2` only  
**Authoritative companions:**  
- `TAWALA_CORE_DESIGN.md` (what Core is)  
- Architecture set: CORE_ARCHITECTURE, DOMAIN_MODEL, SECURITY_MODEL, DOMAIN_BOUNDARIES, DOMAIN_CONTRACTS  
- `MERGE_POLICY.md` (never merge into `main` / `dev`)  
- `V2_CORE_MILESTONES.md` (execution board)

**Purpose of this document:**  
Turn the architecture into a **concrete development plan**: repository structure, every Core model, schemas, service classes, API endpoints, integration rules, database design, CI, images, and acceptance tests — so any engineer or AI agent can resume work even if `.trackers/` are stale.

**Rule:** If implementation and this spec disagree, **stop and update the spec** (or get approval to change it). Do not invent architecture in code.

---

# PART A — HOW TO USE THIS DOCUMENT

## A.1 Resume protocol (for any agent)

1. Confirm branch is `core/v2` (never implement Core on `main`/`dev`).  
2. Read in order: `MERGE_POLICY.md` → this SPEC → `TAWALA_CORE_DESIGN.md` → `V2_CORE_MILESTONES.md`.  
3. Ignore product code on `main`; it is not a source of truth for Core.  
4. Implement only milestones marked approved in the board / task tracker.  
5. Update `.trackers/*` in the same commits as work.  
6. Never open a PR from `core/**` → `main` or `dev`.

## A.2 What “done” means for Core

Core is complete when:

- All models/schemas/endpoints in **Part D–F** exist and match this spec  
- Isolation + IDOR + RBAC + membership suites in **Part H** pass in CI  
- Docker image builds  
- CI is green on `core/v2`  
- Compatibility matrix vs architecture docs is updated to MATCH for Core scope  

---

# PART B — ISOLATION: CORE CAN NEVER MERGE INTO PRODUCT

## B.1 Layers (all required)

| Layer | Mechanism | Owner |
|-------|-----------|--------|
| 1 | `MERGE_POLICY.md` on `core/v2` | Repo (done) |
| 2 | `AGENTS.md` forbids core→main/dev | Repo (done) |
| 3 | GitHub Action fails PR if head is `core/**` and base is `main` or `dev` | Repo (done: `block-core-merge-to-product.yml`) |
| 4 | **GitHub branch protection on `main`** | **Human admin** |
| 5 | Optional: branch protection on `dev` same rule | Human admin |
| 6 | No shared release pipeline that promotes `core/v2` images to product clusters | Ops |

## B.2 Exact GitHub settings (operator checklist)

On repository **NetHub-Ltd/TawalaKE**:

**Settings → Branches → Branch protection rule for `main`:**

- [ ] Require a pull request before merging  
- [ ] Require status checks to pass (include `Block core merge into product` / job `guard`)  
- [ ] Restrict who can push  
- [ ] **Do not** allow `core/v2` maintainers to bypass for product merges  
- Optional advanced: use rulesets to **block** pull requests where head branch name matches `core/**`

Repeat for `dev` if desired.

**Verify:**

1. Open a test PR `core/v2` → `main` (do not merge).  
2. CI job must fail with MERGE_POLICY message.  
3. Close the PR without merging.

## B.3 Agent / human hard rules

```text
FORBIDDEN:
  git checkout main && git merge core/v2
  gh pr create --base main --head core/v2
  gh pr create --base dev --head core/v2
  Cherry-pick Core model commits into product branches without a separate approved migration program

ALLOWED:
  PRs targeting core/v2
  Work only on core/v2 (and future core/* design branches)
  Delete/archive core/v2 without touching main
```

## B.4 Image / deploy isolation

- Core images must use a **distinct name**, e.g. `tawala-core` (never overwrite `tawala-api` product tags).  
- Core CI must **not** push to the product production ImageRepository/ImagePolicy used by k3s for the live POS.  
- Document registry path in milestones when CI is added.

---

# PART C — REPOSITORY & RUNTIME STRUCTURE

## C.1 Target tree on `core/v2` (after structure milestone)

```text
TawalaKE/                          # repo root on core/v2
├── MERGE_POLICY.md
├── AGENTS.md
├── README.md
├── .trackers/
│   ├── repo-state.md
│   ├── task.md
│   └── rollback.md
├── docs/
│   └── architecture/
│       ├── TAWALA_CORE_DESIGN.md
│       ├── TAWALA_CORE_DEVELOPMENT_SPEC.md   # this file
│       └── V2_CORE_MILESTONES.md
├── .github/
│   └── workflows/
│       ├── block-core-merge-to-product.yml
│       ├── core-ci.yml              # lint, test, typecheck
│       └── core-image.yml           # build/push tawala-core image (non-prod registry path)
├── backend/                         # Core backend only (no product POS)
│   ├── pyproject.toml               # or requirements + uv.lock
│   ├── Dockerfile
│   ├── alembic/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory
│   │   ├── api/
│   │   │   ├── deps.py              # TenantContext, auth deps
│   │   │   ├── router.py            # aggregates Core routers
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── identity.py
│   │   │       ├── memberships.py
│   │   │       ├── security.py
│   │   │       ├── organization.py
│   │   │       ├── parties.py
│   │   │       ├── catalog.py
│   │   │       └── audit.py
│   │   ├── core_platform/           # implementation of Core modules
│   │   │   ├── identity/
│   │   │   ├── security/
│   │   │   ├── organization/
│   │   │   ├── parties/
│   │   │   ├── catalog/
│   │   │   ├── events/
│   │   │   ├── audit/
│   │   │   ├── configuration/
│   │   │   └── shared/
│   │   ├── models/                  # SQLModel/SQLAlchemy tables (Core only)
│   │   ├── schemas/                 # Pydantic request/response
│   │   └── db/                      # session, engine
│   └── tests/
│       ├── isolation/
│       ├── idor/
│       ├── rbac/
│       ├── membership/
│       └── unit/
└── (no frontend/)
```

## C.2 Technology choices (Core implementation)

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python ≥ 3.12 | Align with future domain modules; type-friendly |
| API | FastAPI | Async, OpenAPI, deps for authz |
| ORM | SQLModel + SQLAlchemy 2 async | Models + validation adjacency |
| DB | PostgreSQL | Required for multi-tenant production |
| Migrations | Alembic | Additive only |
| Validation | Pydantic v2 | Schemas |
| Tests | pytest + httpx AsyncClient | API + isolation suites |
| Cache (optional Phase 2+) | Redis | Permission cache only after correctness proven |
| Containers | Docker multi-stage | `tawala-core` image |
| CI | GitHub Actions on `core/v2` | No deploy to product k3s |

## C.3 Integration rules

1. **In-process modular monolith** — Core packages call each other via service interfaces, not raw cross-table writes from routes.  
2. **Routes → Services → Repositories/ORM** — routes do not embed business rules.  
3. **TenantContext** injected via FastAPI deps on every protected route.  
4. **No domain packages** (sales/inventory/payments) on this branch until Core complete gate.  
5. **Events:** write domain_events + outbox in same DB transaction as state change when emitting.  
6. **Idempotency:** commands that create resources accept optional `idempotency_key` (unique per business where specified).

---

# PART D — DATABASE MODELS (EVERY CORE TABLE)

Conventions:

- PK: `id UUID PRIMARY KEY`  
- Tenant: `business_id UUID NOT NULL` on all business-owned tables  
- Timestamps: `created_at`, `updated_at` (timestamptz)  
- Soft patterns: `status` enums; `deleted_at` only where archive is used  
- No `tenant_id` column (Business is the only tenant id)

## D.1 Identity

### `users`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| email | CITEXT | UNIQUE NULLABLE |
| phone | VARCHAR(32) | UNIQUE NULLABLE |
| display_name | VARCHAR(255) | NULLABLE |
| status | ENUM(active, disabled, pending) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

Check: at least one of email or phone NOT NULL.

### `credentials`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK users ON DELETE CASCADE, UNIQUE for password type |
| type | ENUM(password, …) | NOT NULL |
| secret_hash | TEXT | NOT NULL (password hash) |
| created_at | TIMESTAMPTZ | NOT NULL |
| rotated_at | TIMESTAMPTZ | NULLABLE |

### `sessions`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK users |
| token_hash | TEXT | NOT NULL UNIQUE |
| expires_at | TIMESTAMPTZ | NOT NULL |
| revoked_at | TIMESTAMPTZ | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |
| user_agent | TEXT | NULLABLE |
| ip | INET | NULLABLE |

## D.2 Organization

### `businesses`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| name | VARCHAR(255) | NOT NULL |
| slug | VARCHAR(64) | UNIQUE NULLABLE |
| status | ENUM(active, suspended, closed) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

### `branches`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| code | VARCHAR(64) | NULLABLE |
| status | ENUM(active, inactive) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(business_id, name)` or `(business_id, code)` where code present.  
INDEX `(business_id)`.

### `locations`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| branch_id | UUID | FK branches, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| kind | ENUM(shop, warehouse, storeroom, office, other) | NOT NULL DEFAULT other |
| status | ENUM(active, inactive) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

INDEX `(business_id)`, `(branch_id)`.

## D.3 Security

### `memberships`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| user_id | UUID | FK users, NOT NULL |
| status | ENUM(invited, active, suspended, revoked) | NOT NULL |
| invited_at | TIMESTAMPTZ | NULLABLE |
| activated_at | TIMESTAMPTZ | NULLABLE |
| revoked_at | TIMESTAMPTZ | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(business_id, user_id)`. INDEX `(user_id)`, `(business_id)`.

### `permissions`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| code | VARCHAR(128) | UNIQUE NOT NULL (e.g. `catalog.product.create`) |
| description | TEXT | NULLABLE |

### `roles`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| name | VARCHAR(128) | NOT NULL |
| is_system | BOOLEAN | NOT NULL DEFAULT false |
| created_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(business_id, name)`.

### `role_permissions`
| Column | Type | Constraints |
|--------|------|-------------|
| role_id | UUID | FK roles |
| permission_id | UUID | FK permissions |
| PK | (role_id, permission_id) | |

### `membership_roles`
| Column | Type | Constraints |
|--------|------|-------------|
| membership_id | UUID | FK memberships |
| role_id | UUID | FK roles |
| PK | (membership_id, role_id) | |

### `scope_assignments`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| membership_id | UUID | FK memberships, NOT NULL |
| branch_id | UUID | FK branches NULLABLE |
| location_id | UUID | FK locations NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |

Rule: if both null → business-wide scope for that membership’s permissions.  
If set, branch/location must belong to same `business_id` as membership (enforce in service).

## D.4 Parties

### `parties`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| kind | ENUM(person, organization) | NOT NULL |
| display_name | VARCHAR(255) | NOT NULL |
| primary_email | CITEXT | NULLABLE |
| primary_phone | VARCHAR(32) | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

Note: Party is **not** tenant-owned alone; relationship to business is via link.  
Optional later: platform-global party vs per-business copy — **v1 uses links**.

### `party_business_links`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| party_id | UUID | FK parties, NOT NULL |
| relationship | ENUM(customer, supplier, employee, member, other) | NOT NULL |
| status | ENUM(active, inactive) | NOT NULL DEFAULT active |
| external_ref | VARCHAR(128) | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(business_id, party_id, relationship)`. INDEX `(business_id, relationship)`.

## D.5 Catalog (identity only — NO quantity)

### `categories`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| parent_id | UUID | FK categories NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |

### `products`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| sku | VARCHAR(128) | NULLABLE |
| barcode | VARCHAR(128) | NULLABLE |
| category_id | UUID | FK categories NULLABLE |
| unit | VARCHAR(32) | NOT NULL DEFAULT 'ea' |
| status | ENUM(active, archived) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

**FORBIDDEN column:** `quantity`, `stock`, `on_hand`.  
UNIQUE `(business_id, sku)` WHERE sku IS NOT NULL.

### `services`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| name | VARCHAR(255) | NOT NULL |
| code | VARCHAR(128) | NULLABLE |
| status | ENUM(active, archived) | NOT NULL DEFAULT active |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

## D.6 Events, outbox, audit, config

### `domain_events`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK (event_id) |
| event_type | VARCHAR(128) | NOT NULL |
| occurred_at | TIMESTAMPTZ | NOT NULL |
| business_id | UUID | NULLABLE (some platform events) |
| actor_user_id | UUID | NULLABLE |
| request_id | UUID | NULLABLE |
| aggregate_type | VARCHAR(64) | NOT NULL |
| aggregate_id | UUID | NOT NULL |
| version | INT | NOT NULL DEFAULT 1 |
| payload | JSONB | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

Immutable: no UPDATE API for payload.

### `outbox_entries`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| event_id | UUID | FK domain_events UNIQUE |
| status | ENUM(pending, published, failed) | NOT NULL DEFAULT pending |
| attempts | INT | NOT NULL DEFAULT 0 |
| next_attempt_at | TIMESTAMPTZ | NULLABLE |
| last_error | TEXT | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |

### `audit_records`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | NULLABLE |
| actor_user_id | UUID | NULLABLE |
| action | VARCHAR(128) | NOT NULL |
| resource_type | VARCHAR(64) | NOT NULL |
| resource_id | UUID | NULLABLE |
| outcome | ENUM(success, denied, error) | NOT NULL |
| request_id | UUID | NULLABLE |
| before | JSONB | NULLABLE |
| after | JSONB | NULLABLE |
| reason | TEXT | NULLABLE |
| occurred_at | TIMESTAMPTZ | NOT NULL |

Append-only for normal roles.

### `business_configs`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| business_id | UUID | FK businesses, NOT NULL |
| key | VARCHAR(128) | NOT NULL |
| value | JSONB | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(business_id, key)`.

## D.7 Seed data

- System `permissions` rows for Core codes (see Part F).  
- No product/demo businesses required in CI (tests create their own).

---

# PART E — SCHEMAS & SERVICE CLASSES

## E.1 Shared types (`core_platform.shared`)

```text
TenantContext
  business_id: UUID
  actor_user_id: UUID
  membership_id: UUID
  branch_id: Optional[UUID]
  location_id: Optional[UUID]
  permissions: frozenset[str]
  request_id: UUID

Money          # optional later; not required for Core identity
DomainError    # NotFound, Forbidden, Conflict, ValidationFailed, AlreadyProcessed
```

## E.2 Service classes (one primary service per module)

| Module | Class | Responsibility |
|--------|-------|----------------|
| identity | `IdentityService` | register/authenticate user, sessions, revoke |
| security | `MembershipService` | invite/activate/suspend/revoke |
| security | `AuthorizationService` | resolve permissions, assert permission+scope |
| security | `RoleService` | CRUD roles, attach permissions (business-scoped) |
| organization | `OrganizationService` | business/branch/location CRUD |
| parties | `PartyService` | create party, link to business |
| catalog | `CatalogService` | product/service/category CRUD (no stock) |
| events | `EventService` | append event + outbox |
| audit | `AuditService` | append audit record |
| configuration | `ConfigService` | get/set business config |

Routes call services only; services enforce tenant + authz using `AuthorizationService`.

## E.3 Pydantic schemas (naming)

Request/Response pairs per resource, e.g.:

```text
UserCreate, UserRead
MembershipInvite, MembershipRead
BusinessCreate, BusinessRead
BranchCreate, BranchRead
LocationCreate, LocationRead
PartyCreate, PartyRead
PartyLinkCreate, PartyLinkRead
ProductCreate, ProductUpdate, ProductRead
ServiceCreate, ServiceRead
RoleCreate, RoleRead
PermissionRead
AuditRecordRead
```

All write schemas strip client-supplied `business_id` where context supplies it (or require match to context).

---

# PART F — API ENDPOINTS (CORE SURFACE)

Base prefix: `/api/v1`  
Auth: Bearer session/access token resolving to User; protected routes require `TenantContext`.

## F.1 Health

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | liveness |
| GET | `/ready` | none | DB connectivity |

## F.2 Identity

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| POST | `/auth/register` | none | — | create user (platform) |
| POST | `/auth/login` | none | — | create session |
| POST | `/auth/logout` | user | — | revoke session |
| GET | `/auth/me` | user | — | current user |

## F.3 Organization

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| POST | `/businesses` | user | platform or bootstrap rule | create business + owner membership |
| GET | `/businesses/{id}` | ctx | `organization.business.read` | get |
| PATCH | `/businesses/{id}` | ctx | `organization.business.update` | update |
| POST | `/businesses/{id}/branches` | ctx | `organization.branch.create` | create branch |
| GET | `/businesses/{id}/branches` | ctx | `organization.branch.read` | list |
| POST | `/branches/{id}/locations` | ctx | `organization.location.create` | create location |
| GET | `/branches/{id}/locations` | ctx | `organization.location.read` | list |

All IDs verified against `ctx.business_id` (IDOR deny).

## F.4 Memberships & security

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| POST | `/businesses/{id}/memberships` | ctx | `security.membership.invite` | invite |
| POST | `/memberships/{id}/activate` | user/ctx | rules | activate |
| POST | `/memberships/{id}/suspend` | ctx | `security.membership.suspend` | suspend |
| POST | `/memberships/{id}/revoke` | ctx | `security.membership.revoke` | revoke |
| GET | `/businesses/{id}/memberships` | ctx | `security.membership.read` | list |
| POST | `/businesses/{id}/roles` | ctx | `security.role.manage` | create role |
| POST | `/roles/{id}/permissions` | ctx | `security.role.manage` | attach permission |
| POST | `/memberships/{id}/roles` | ctx | `security.role.assign` | assign role |
| GET | `/me/permissions` | ctx | — | effective permissions |

## F.5 Parties

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| POST | `/parties` | ctx | `parties.create` | create party |
| POST | `/parties/{id}/links` | ctx | `parties.link` | link to business + relationship |
| GET | `/parties/{id}` | ctx | `parties.read` | get if linked to business |
| GET | `/businesses/{id}/parties` | ctx | `parties.read` | list links |

## F.6 Catalog

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| POST | `/products` | ctx | `catalog.product.create` | create |
| PATCH | `/products/{id}` | ctx | `catalog.product.update` | update |
| GET | `/products/{id}` | ctx | `catalog.product.read` | get |
| GET | `/products` | ctx | `catalog.product.read` | search/list |
| POST | `/services` | ctx | `catalog.service.create` | create |
| GET | `/services/{id}` | ctx | `catalog.service.read` | get |

**No** endpoints that set stock quantity.

## F.7 Audit

| Method | Path | Auth | Permission | Purpose |
|--------|------|------|------------|---------|
| GET | `/audit-records` | ctx | `audit.read` | filtered list |

## F.8 Core permission codes (seed)

```text
organization.business.read
organization.business.update
organization.branch.create
organization.branch.read
organization.location.create
organization.location.read
security.membership.invite
security.membership.read
security.membership.suspend
security.membership.revoke
security.role.manage
security.role.assign
parties.create
parties.link
parties.read
catalog.product.create
catalog.product.update
catalog.product.read
catalog.service.create
catalog.service.read
audit.read
```

---

# PART G — IMPLEMENTATION SEQUENCE (HOW CODE IS BUILT)

Order is mandatory to avoid circular dependencies:

```text
1. Repo structure + pyproject + Dockerfile + empty FastAPI app + /health
2. DB engine/session + Alembic
3. models: users, credentials, sessions
4. IdentityService + auth routes + tests
5. models: businesses, branches, locations
6. OrganizationService + routes + isolation tests
7. models: memberships, permissions, roles, …
8. MembershipService + AuthorizationService + RBAC tests
9. models: parties, party_business_links
10. PartyService + routes + IDOR tests
11. models: products, services, categories
12. CatalogService + routes + “no quantity” schema tests
13. domain_events, outbox, audit_records, business_configs
14. EventService + AuditService + emit on key mutations
15. Full isolation/IDOR/RBAC suite green
16. core-ci.yml + core-image.yml green
```

---

# PART H — TEST PLAN (ACCEPTANCE)

| Suite | Location | Must prove |
|-------|----------|------------|
| Isolation | `tests/isolation/` | User in Business A cannot read B’s branch/product/party |
| IDOR | `tests/idor/` | Random UUIDs return 404/403, never leak existence across tenants where policy requires |
| Membership | `tests/membership/` | revoked/suspended cannot call protected routes |
| RBAC | `tests/rbac/` | missing permission → 403; granted → 200 |
| Scope | `tests/scope/` | branch-scoped membership denied on other branch |
| Catalog boundary | `tests/catalog/` | ProductCreate rejects quantity field; DB has no quantity column |
| Auth | `tests/identity/` | login/logout/session expiry |
| Audit | `tests/audit/` | revoke membership writes audit row |

CI must run the full suite on every push to `core/v2`.

---

# PART I — CI & IMAGES

## I.1 `core-ci.yml` (on push/PR to `core/v2`)

Jobs:

1. **lint** — ruff / equivalent  
2. **typecheck** — mypy or pyright on `app/`  
3. **test** — pytest with Postgres service container  
4. **migrate** — alembic upgrade head against test DB  

No job deploys to product k3s.

## I.2 `core-image.yml`

- Build Docker image tagged `tawala-core:<git-sha>`  
- Push only to registry path reserved for Core (document path in milestone when credentials exist)  
- **Never** tag as product `tawala-api` production image  

## I.3 Local verification commands (to document in README)

```text
cd backend
uv sync   # or pip install
alembic upgrade head
pytest
docker build -t tawala-core:local .
```

---

# PART J — MILESTONE MAP (FOR V2 BOARD / ISSUES)

Use these as GitHub issues on project board **Tawala Core V2** (labels: `core`, `phase-N`).

| Milestone ID | Title | Deliverables | Acceptance |
|--------------|-------|--------------|--------------|
| M0 | Isolation confirmed | MERGE_POLICY, CI guard, admin branch protection checklist | Test PR core→main fails CI |
| M1 | Backend skeleton | Tree Part C, FastAPI health, pyproject, Dockerfile | `/health` 200 in container |
| M2 | CI pipeline | `core-ci.yml` | Lint+test jobs green on empty/skeleton |
| M3 | DB + Alembic | Engine, first migration | upgrade head works |
| M4 | Identity | D.1 models, schemas, IdentityService, F.2 routes | Auth tests pass |
| M5 | Organization | D.2 models, OrganizationService, F.3 | Isolation tests pass |
| M6 | Security | D.3 models, Membership + Authz + Role services, F.4 | RBAC + membership tests pass |
| M7 | Parties | D.4 models, PartyService, F.5 | IDOR + link tests pass |
| M8 | Catalog | D.5 models, CatalogService, F.6 | No-quantity tests pass |
| M9 | Events + Audit + Config | D.6 models, services, audit on revoke | Audit + event tests pass |
| M10 | Image build | `core-image.yml`, `tawala-core` image | Image builds in CI |
| M11 | Core complete gate | Full Part H suite, matrix doc | All green; design MATCH |

Each GitHub issue body should link to the relevant **Part D/E/F** section of this SPEC.

---

# PART K — EXPLICIT NON-GOALS

- Frontend / BFF / Next.js  
- Sales, stock quantity, payments, accounting tables  
- Merging into `main` or `dev`  
- Reusing product `models.py`  
- Deploying Core image as replacement for live POS API without a separate migration program  

---

# PART L — TRACEABILITY

| Spec part | Architecture source |
|-----------|---------------------|
| D.1–D.3 | SECURITY_MODEL, DOMAIN_MODEL Identity/Org |
| D.4 | DOMAIN_MODEL Party |
| D.5 | DOMAIN_BOUNDARIES Catalog ≠ Inventory |
| D.6 | DOMAIN_CONTRACTS events, SECURITY audit |
| F | DOMAIN_CONTRACTS command/query style |
| B | Isolation principles SECURITY_MODEL |

---

# PART M — ACCEPTANCE OF THIS SPEC

This DEVELOPMENT SPEC is accepted when:

- [ ] Isolation layers B.1–B.2 understood; admin will apply GitHub protection  
- [ ] Model list D.* agreed (including no stock on products)  
- [ ] Endpoint list F.* agreed as Core v1 surface  
- [ ] Sequence G and milestones J agreed  
- [ ] Open questions from CORE_DESIGN §12 resolved (or defaults OK)  

**Then** implementation proceeds milestone-by-milestone on `core/v2` only.

---

**Status:** DRAFT 0.1.0 — ready for review before any application code.

**End of TAWALA_CORE_DEVELOPMENT_SPEC.md**
