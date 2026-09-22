# V2 Core Program — Milestones & Issues

**GitHub Project board (source of truth for status):**  
https://github.com/orgs/NetHub-Ltd/projects/5

| Milestone | Issue | Board status |
|-----------|-------|--------------|
| M0.4 Branch protection (operator) | #245 | Todo |
| M0.5 Project board linked | #246 | Done (closed) |
| M1 Backend skeleton | #247 | Done (closed) |
| M2 Core CI | #248 | Done (closed) |
| M3 DB + Alembic | #249 | Done |
| M4 Identity | #250 | Done |
| M5 Organization | #251 | Done |
| M6 Membership / RBAC | #252 | Done |
| M7 Parties | #253 | Done |
| M8 Catalog | #254 | Done |
| M9 Events / Audit / Config | #255 | Done |
| M10 Image `tawala-core` | #256 | Done |
| M11 Core complete gate | #257 | Done |

**Agent rule:** Read the Project board + open `core` issues. Do not wait for chat to say “what’s next.” Next work = lowest open Todo/In Progress issue on the board that is not blocked. Always on branch `core/v2`. Never PR into `main`/`dev`.

---

# V2 Core Program — Milestones & Issues

**Branch:** `core/v2`  
**Spec:** `TAWALA_CORE_DEVELOPMENT_SPEC.md` (authoritative for models, endpoints, CI)  
**Design:** `TAWALA_CORE_DESIGN.md`  
**Isolation:** `MERGE_POLICY.md`

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

Agents: if `.trackers/` are stale, follow **SPEC Part A resume protocol** and this board.

---

## Phase 0 — Isolation & documentation

| ID | Milestone | Status | Acceptance |
|----|-----------|--------|------------|
| M0.1 | `core/v2` clean-slate + MERGE_POLICY + CI merge guard | [x] | Product tree gone; guard workflow present |
| M0.2 | CORE_DESIGN + DEVELOPMENT_SPEC drafted | [x] | Docs on branch |
| M0.3 | Spec accepted (models, endpoints, sequence) | [x] | User: spec approved 2026-09-19 |
| M0.4 | GitHub branch protection on `main` (operator) | [ ] | core→main PR cannot merge |
| M0.5 | GitHub Project board + issues M1–M11 created | [ ] | Issues link to SPEC sections |

---

## Phase 1 — Structure, CI, images foundation

| ID | Milestone | Status | Acceptance | Tests / checks |
|----|-----------|--------|------------|----------------|
| M1 | Backend skeleton | [x] | Tree per SPEC Part C; FastAPI `/health` | pytest health 2 passed |
| M2 | Core CI pipeline | [x] | `core-ci.yml` green (user confirmed) | CI green |
| M3 | DB + Alembic bootstrap | [x] | Settings, async engine, session, baseline migration, /ready DB report | `alembic upgrade head` |
| M10 | Image build pipeline | [x] | Dockerfile multi-stage + core-image.yml smoke /health | Image builds; **not** product `tawala-api` |

Note: M10 may proceed once M1 skeleton exists.

---

## Phase 2 — Identity & organization

| ID | Milestone | Status | Acceptance | Tests |
|----|-----------|--------|------------|-------|
| M4 | Identity models + auth API | [x] | users/credentials/sessions, register/login/logout/me | `tests/identity/` |
| M5 | Organization models + API | [x] | Business/Branch/Location + membership gate | `tests/isolation/` start |

---

## Phase 3 — Security

| ID | Milestone | Status | Acceptance | Tests |
|----|-----------|--------|------------|-------|
| M6 | Membership, roles, permissions, authz | [x] | BaseMixin + RBAC tables/services/routes | membership, rbac, scope suites |

---

## Phase 4 — Parties & catalog

| ID | Milestone | Status | Acceptance | Tests |
|----|-----------|--------|------------|-------|
| M7 | Parties + links | [x] | Party + PartyBusinessLink, IDOR-safe get | IDOR + list by business |
| M8 | Catalog products/services (no quantity) | [x] | Product/Service/Category; schema rejects stock | catalog rejects quantity |

---

## Phase 5 — Events, audit, config, complete

| ID | Milestone | Status | Acceptance | Tests |
|----|-----------|--------|------------|-------|
| M9 | Events, outbox, audit, config | [x] | emit+outbox; audit on revoke; configs | Audit on revoke; event append |
| M11 | Core complete gate | [x] | Matrix + 22 tests; residual risks documented | Full unit/contract suite |

---

## Issue template (copy into GitHub issues)

```markdown
## Spec reference
TAWALA_CORE_DEVELOPMENT_SPEC.md — section(s): …

## Deliverables
- [ ] Models / migrations
- [ ] Schemas
- [ ] Service class(es)
- [ ] Routes
- [ ] Tests listed in milestone

## Out of scope
- Frontend
- Product main/dev merge
- Sales/Inventory/Payments

## Acceptance
CI green on core/v2 for this milestone’s tests.
```

---

## Non-merge reminder

```text
Never: PR core/v2 → main or dev
Never: tag Core image as production tawala-api
Never: copy product models into Core
```

---

## Definition of Core complete

- M0–M11 acceptance criteria met
- SPEC Part H suites pass
- Isolation layers active (policy + CI + branch protection)
- Trackers current on branch tip
