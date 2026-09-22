# Agent Operating Instructions — Core V2 Branch

> Applies only on branch `core/v2` (and future `core/**`).

## 1. Isolation (non-negotiable)

- **Never** open, approve, or suggest a pull request from `core/**` into `main` or `dev`.
- **Never** merge Core into product branches.
- **Never** copy product models, CRUD, routes, or frontend from `main` into this branch.
- Read and obey `MERGE_POLICY.md`.

## 2. What we are building

**Tawala Core blueprint and later implementation** — not the current POS product.

Core is defined by the architecture documents. The design document is:

`docs/architecture/TAWALA_CORE_DESIGN.md`

Until that design is accepted, do not implement domain models or APIs beyond scaffolding required by the design process.

## 3. No frontend

This branch has no frontend. Do not add Next.js, UI kits, or BFF routes here.

## 4. Trackers

Maintain:

```text
.trackers/repo-state.md
.trackers/task.md
.trackers/rollback.md
```

Update them in the same commits as design or code changes.

## 5. Engineer Mode

Proposal → approval → implement on this branch only. Protect product `main`.

## 6. Priority

Correct tenancy, security, and domain boundaries > speed > reuse of old code.
