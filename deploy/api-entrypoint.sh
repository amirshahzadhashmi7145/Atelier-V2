#!/bin/sh
set -e

# All persistent state lives under ATELIER_DATA_DIR, which docker-compose bind-mounts
# at the SAME path on the host and in this container. That identical path is what makes
# the per-task sandbox work: the API asks the host Docker daemon to mount a project
# folder, and the daemon resolves the path on the host.
: "${ATELIER_DATA_DIR:=/srv/atelier}"
mkdir -p "$ATELIER_DATA_DIR/db" "$ATELIER_DATA_DIR/projects" "$ATELIER_DATA_DIR/home"

# The app self-creates its schema from DATABASE_URL on first use (no migration step).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
