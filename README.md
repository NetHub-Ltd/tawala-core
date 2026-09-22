# Tawala Core V2

**Branch:** `core/v2`  
**Status:** Core foundation **complete** (M11 gate)  
**Isolation:** Never merge into `main` or `dev` — see `MERGE_POLICY.md`

## Board
https://github.com/orgs/NetHub-Ltd/projects/5

## Spec & matrix
- `docs/architecture/TAWALA_CORE_DEVELOPMENT_SPEC.md`
- `docs/architecture/TAWALA_CORE_DESIGN.md`
- `docs/architecture/V2_CORE_MILESTONES.md`
- `docs/architecture/CORE_COMPATIBILITY_MATRIX.md`

## Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --port 8000
curl http://127.0.0.1:8000/health
pytest
```

## Image
`tawala-core:<sha>` only — never `tawala-api`.

## No frontend
Core has no UI on this branch by design.
