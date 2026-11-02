# Contributing to Agent Studio

Thanks for your interest in contributing! This guide covers the dev setup and the
conventions the project follows.

## Development setup

See the [Quick start](README.md#quick-start) for installing and running the API and
web app. In short:

```bash
# API
cp api/.env.example api/.env
uv sync --directory api --python 3.12
uv run --directory api alembic upgrade head
uv run --directory api uvicorn app.main:app --host 127.0.0.1 --port 8000

# Web
cp web/.env.example web/.env.local
pnpm --dir web install
pnpm --dir web dev
```

## Before you open a pull request

Run the full checks locally — CI runs the same three jobs (api, web, secrets):

```bash
uv run --directory api pytest
pnpm --dir web typecheck
pnpm --dir web lint
pnpm --dir web test
pnpm --dir web test:e2e
python3 scripts/scan_secrets.py
```

- **API**: FastAPI + SQLAlchemy over SQLite. Add tests under `api/tests/`.
- **Web**: Next.js + React + TypeScript. If you change an API shape, update
  `openapi/agent-studio.yaml` and regenerate the types.
- Keep changes focused; match the style, naming, and comment density of the
  surrounding code.

## Commit and branch conventions

- Branch off `main`; use short prefixes like `feat/…`, `fix/…`, `chore/…`, `docs/…`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for messages,
  e.g. `fix(preview): reinstall stale deps before serving`.
- One logical change per PR, with a clear description of the problem and the fix.

## Never commit secrets

API keys and tokens must never be committed. `api/.env` and `PROJECTS_DIR/.secrets`
are gitignored; keys belong in **Settings → Providers** (encrypted at rest) or in your
local `.env`. The `secrets` CI job and `scripts/scan_secrets.py` will flag common key
patterns. If you believe a secret was exposed, see [SECURITY.md](SECURITY.md).

## Reporting bugs and requesting features

Open a GitHub issue with steps to reproduce (for bugs) or the use case and proposed
behavior (for features). Include logs or screenshots where helpful — with any secrets
redacted.

## License

By contributing, you agree that your contributions are licensed under the project's
[MIT License](LICENSE).
