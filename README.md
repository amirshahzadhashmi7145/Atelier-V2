# Agent Studio

Chat on `/chat` sends a task to an agent. The API calls OpenAI, and the agent works in a folder on this machine. The same chat can later host a supervisor, because a task is assigned by one function, `route_task`.

## Run the API and the web app

```bash
cp api/.env.example api/.env
uv sync --directory api --python 3.12
uv run --directory api alembic upgrade head
uv run --directory api uvicorn app.main:app --host 127.0.0.1 --port 8000

cp web/.env.example web/.env.local
pnpm --dir web install
pnpm --dir web dev
```

Open http://127.0.0.1:3000/chat

Put the OpenAI key in `api/.env` as `OPENAI_API_KEY`. That file is gitignored. The browser never receives the key. `web/.env.local` only needs the public URL:

```bash
NEXT_PUBLIC_USE_MOCKS=false
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Mocks stay on for `pnpm test` and the studio Playwright project. The chat Playwright project runs against this API with the model mocked at the gateway.

## Where projects live

`PROJECTS_DIR` in `api/.env` defaults to `~/AgentStudio/projects`. Creating a project creates the folder and runs `git init`. Open folder copies that path.

## Connect a GitHub repo

On New project, add the repository URL. Paste a token in the form, or set `GITHUB_TOKEN` in `api/.env`. The token is stored by reference (`tokenRef`): a pasted token goes to `PROJECTS_DIR/.secrets` with mode 0600 and is never returned or sent to the model. When a project is connected, a task commits on a branch, pushes, and opens a pull request through the GitHub API.

## DEV LOCAL MODE

If Docker does not answer, or `FORCE_LOCAL=1` is set, commands run in the project folder on this machine. A write outside that folder is refused. The chat shows a yellow banner. This mode is for the developer's own machine.

When Docker is available, each run uses an unprivileged container with only the project mounted at `/workspace`. The container image is `node:22-bookworm`. The container sits on an internal network and reaches the internet only through a proxy that allows the npm registry, GitHub, and the preview host. A fetch to any other host fails. DEV LOCAL MODE is unchanged when Docker does not answer.

## Tests

```bash
uv run --directory api pytest
pnpm --dir web typecheck
pnpm --dir web lint
pnpm --dir web test
pnpm --dir web test:e2e
```

`RUN_REAL_LLM_TESTS=1 uv run --directory api pytest` also runs one real OpenAI call: a fresh project asked to create a landing page with a hero and three feature cards. That test is skipped otherwise, including in CI.
