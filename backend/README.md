# Tawala Core backend

**Branch:** `core/v2` only  
**Image name:** `tawala-core` (never `tawala-api`)

Implements the platform foundation defined in:

- `docs/architecture/TAWALA_CORE_DEVELOPMENT_SPEC.md`
- `docs/architecture/TAWALA_CORE_DESIGN.md`

## Local run (skeleton)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

## Tests

```bash
pytest
```

## Docker

**Python:** 3.13 (image base `python:3.13-slim`).

Build context must be this `backend/` directory (CI does `context: ./backend`):

```bash
# from backend/
docker build -t tawala-core:local .

# from repo root
docker build -t tawala-core:local -f backend/Dockerfile backend
# or use the root Dockerfile:
docker build -t tawala-core:local .
```

```bash
docker run --rm -p 8000:8000 \
  -e DB_HOST=... -e DB_USER=... -e DB_PASSWORD=... -e DB_NAME=... \
  tawala-core:local
```

Do **not** run `docker build -f backend/Dockerfile .` from the repo root — that uses the wrong context and fails with missing `app/`, `start.sh`, `pyproject.toml`.

## Isolation

See repository root `MERGE_POLICY.md`. Do not merge this branch into `main` or `dev`.
