# Agent Studio

Agent Studio is a self-hosted, multi-agent coding platform. You describe what you
want in a chat; a **Team Lead** plans the work, dispatches it to specialist worker
agents (Frontend, Backend, …), reviews their output, and opens a pull request. The
agents run in a sandbox and edit a real project folder on your machine. You bring
your own model API key — nothing is sent to a hosted backend.

- **Chat → working code.** A task on `/chat` is planned, built, reviewed, and (optionally) pushed to GitHub as a PR.
- **A team, not one bot.** Supervisors plan and review; workers write code inside role-scoped zones. Roles are data, not hard-coded paths.
- **Bring your own model.** OpenAI or Google Gemini, configured per agent. Keys are stored encrypted at rest and never reach the browser.
- **Sandboxed execution.** Runs happen in an unprivileged container with egress limited to the npm registry, GitHub, and the preview host. A local fallback mode is available for solo dev machines.
- **Live preview.** Projects serve a dev preview you can open from the UI.

> **Status:** open source under the [MIT License](LICENSE). Starter **team templates**
> (pick a preset team, add your API key, and start) are in progress — see the roadmap below.

## Quick start

Requirements: Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 18+ with
[pnpm](https://pnpm.io/). Docker is optional (enables the sandboxed run mode).

```bash
# API
cp api/.env.example api/.env
uv sync --directory api --python 3.12
uv run --directory api alembic upgrade head
uv run --directory api uvicorn app.main:app --host 127.0.0.1 --port 8000

# Web (in a second terminal)
cp web/.env.example web/.env.local
pnpm --dir web install
pnpm --dir web dev
```

Open <http://127.0.0.1:3000/chat>.

## Add your model API key

You do **not** need to put a key in a file. Open **Settings → Providers** in the app
and paste your **OpenAI** or **Google Gemini** key; it is encrypted at rest and the
browser never receives it. Each agent chooses its own provider and model.

As a fallback for headless setups, you can instead set `OPENAI_API_KEY` or
`GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in `api/.env`. That file is gitignored —
**never commit a real key.**

`web/.env.local` only holds public config:

```bash
NEXT_PUBLIC_USE_MOCKS=false
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Where projects live

`PROJECTS_DIR` in `api/.env` defaults to `~/AgentStudio/projects`. Creating a project
creates the folder and runs `git init`; you can also **import an existing GitHub repo**
by cloning it into a new project. "Open folder" reveals the path on disk.

## Connect a GitHub repo

On a project, add the repository URL and a token (paste it in the form, or set
`GITHUB_TOKEN` in `api/.env`). The token is stored **by reference** — a pasted token
goes to `PROJECTS_DIR/.secrets` with mode `0600`, is never returned to the client, and
never reaches the model. When a project is connected, a completed task commits on a
branch, pushes, and opens a pull request through the GitHub API.

## Execution modes

**Sandboxed (default when Docker is available).** Each run uses an unprivileged
`node:22-bookworm` container with only the project mounted at `/workspace`. The
container sits on an internal network and reaches the internet only through a proxy
that allows the npm registry, GitHub, and the preview host; any other host is refused.

**Local mode.** If Docker does not answer, or `FORCE_LOCAL=1` is set, commands run in
the project folder on this machine, and a write outside that folder is refused. The
chat shows a yellow banner. This mode is intended for your own development machine.

## Tests

```bash
uv run --directory api pytest       # API
pnpm --dir web typecheck
pnpm --dir web lint
pnpm --dir web test                 # web unit (mocks)
pnpm --dir web test:e2e             # Playwright
```

`RUN_REAL_LLM_TESTS=1 uv run --directory api pytest` additionally runs one real model
call; it is skipped otherwise, including in CI.

## Architecture (short)

- **API** (`api/`): FastAPI + SQLAlchemy over SQLite, a LangGraph supervisor, and an
  OpenHands-based runner. Roles, agents, tasks, and runs are JSON documents.
- **Web** (`web/`): Next.js (app router) + React + TypeScript + Tailwind, with
  OpenAPI-generated types and React Query.
- **Gateway**: a LiteLLM-style layer so an agent's provider/model is just data.

## Roadmap

- **Starter team templates** — one-click preset teams (full-stack, frontend-only,
  backend/API, automation); pick one, add your key, and go.
- Broader provider support and model presets.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
dev setup and conventions, and [SECURITY.md](SECURITY.md) to report a vulnerability.

## License

[MIT](LICENSE) © Amir Shahzad Hashmi
