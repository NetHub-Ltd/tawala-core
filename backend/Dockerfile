# Tawala Core — lean multi-platform image (linux/amd64, linux/arm64).
# Tag as tawala-core:<sha> only (MERGE_POLICY). Never tawala-api.
#
# Build context MUST be backend/:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -t tawala-core:local -f backend/Dockerfile backend
#   # single-arch local:
#   docker build -t tawala-core:local -f backend/Dockerfile backend

# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Wheels for asyncpg / psycopg[binary] cover amd64+arm64 on 3.13 — no gcc needed.
COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m venv /install \
    && /install/bin/pip install --upgrade pip \
    && /install/bin/pip install --no-compile .

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH"

WORKDIR /app

# curl only for HEALTHCHECK; no build toolchain in runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --from=builder /install /install
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY start.sh ./start.sh

RUN chmod +x /app/start.sh \
    && chown -R appuser:appuser /app /install

USER appuser

EXPOSE 8000

LABEL org.opencontainers.image.title="tawala-core" \
      org.opencontainers.image.description="Tawala Core platform (core/v2 isolated)" \
      org.opencontainers.image.source="https://github.com/NetHub-Ltd/TawalaKE"

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["/app/start.sh"]
