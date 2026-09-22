#!/usr/bin/env sh
# 1) alembic upgrade head (sync driver from DB_* credentials)
# 2) uvicorn (async driver via app settings)
set -eu

cd "$(dirname "$0")"

if [ -z "${DB_HOST:-}" ] || [ -z "${DB_USER:-}" ] || [ -z "${DB_NAME:-}" ] || [ -z "${DB_PASSWORD+x}" ]; then
  echo "ERROR: Set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (and optional DB_PORT)." >&2
  echo "       Full DATABASE_URL is not accepted — credentials only." >&2
  exit 1
fi

echo "Running alembic upgrade head..."
alembic upgrade head

echo "Starting FastAPI..."
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
