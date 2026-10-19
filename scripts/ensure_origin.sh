#!/usr/bin/env bash
# Restore the GitHub origin remote if a tool emptied .git/config.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="$(tr -d '[:space:]' < "$ROOT/scripts/github-origin.url")"
cd "$ROOT"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi
current="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$current" ]; then
  git remote add origin "$URL"
  exit 0
fi
if [ "$current" != "$URL" ]; then
  git remote set-url origin "$URL"
fi
