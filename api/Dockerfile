# syntax=docker/dockerfile:1

# Agent Studio API (FastAPI). Includes Node 22 because the on-host preview/build
# tooling shells out to npm; the hardened per-task sandbox runs in a SEPARATE
# node:22 container via the mounted Docker socket (see docker-compose.yml).
FROM python:3.12-slim

# Node 22 (for preview/dev-server tooling that runs on the API host).
COPY --from=node:22-bookworm /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# git for project repos, curl for the healthcheck, ca-certificates for TLS egress.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv (Python package manager).
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app/api

# Dependency layer (cached until the lockfile changes).
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code.
COPY api/ ./

COPY deploy/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
RUN chmod +x /usr/local/bin/api-entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/projects >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/api-entrypoint.sh"]
