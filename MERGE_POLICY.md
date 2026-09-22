# MERGE POLICY — Tawala Core V2

**Branch:** `core/v2`  
**Status:** BINDING  
**Effective:** 2026-09-19

---

## Hard rule

**Pull requests and merges from `core/**` into `main` or `dev` are FORBIDDEN.**

This branch exists to design and implement a clean-slate Tawala Core. It must never be merged into product branches by accident or convenience.

| Source branch | Target `main` | Target `dev` | Allowed? |
|---------------|---------------|--------------|----------|
| `core/v2` or `core/**` | — | — | **NO** |
| `main` / `dev` / product topics | `main` / `dev` | as usual | Yes (product workflow) |

---

## Why

- Core is designed from the architecture documents only.
- Product code on `main`/`dev` is intentionally **not** a dependency of Core.
- Accidental merge would mix incompatible models, tenancy fields, and domain boundaries.

---

## Enforcement layers

1. **This document** — human and agent instruction.
2. **AGENTS.md on this branch** — agents must refuse Core → main/dev merges.
3. **CI workflow** — fail PRs that target `main` or `dev` when head branch matches `core/**`.
4. **GitHub branch protection (operator)** — block merges from `core/**` into `main` when available.

---

## Allowed operations on this branch

- Commits and PRs **into** `core/v2` (or future `core/*` design branches).
- Documentation, trackers, Core design, later Core implementation and tests.
- Abandoning the branch without touching `main`/`dev`.

## Forbidden operations

- Opening a PR from `core/v2` → `main`
- Opening a PR from `core/v2` → `dev`
- Cherry-picking Core commits into product branches without an explicit, approved migration program
- Copying product models/routes from `main` into Core “for speed”
- Tagging or pushing Core images as product `tawala-api` (or overwriting production ImagePolicy tags)
- Deploying Core images into the live POS k3s workload as a silent replacement for product API

---

## Image & deploy isolation

| Rule | Detail |
|------|--------|
| Image name | `tawala-core` only (example tag: `tawala-core:<git-sha>`) |
| Product image | `tawala-api` remains product-only on `main`/`dev` pipelines |
| Registry | Use a Core-specific repository path when CI pushes; never the production product tag stream |
| Clusters | Core CI must not auto-deploy to production POS |

See `TAWALA_CORE_DEVELOPMENT_SPEC.md` Part B and Part I.

---

## Operator checklist (GitHub)

1. Branch protection on `main`: require PR + status checks including **Block core merge into product**.
2. Optionally same for `dev`.
3. Verify: open (and close without merging) a test PR `core/v2` → `main`; CI must fail.
4. Do not grant bypass for Core merges into product branches.

---

## Rollback of this branch

Delete or archive `core/v2` on the remote. Product branches are unaffected.

---

**Do not override this policy without a written, approved change to this file and operator confirmation.**
