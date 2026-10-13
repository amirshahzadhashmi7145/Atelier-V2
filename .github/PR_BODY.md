## What

The chat is no longer a mock. A message creates a task and a run, the API calls OpenAI through the gateway, and the agent works in a project folder on this machine. The user sees the summary, the files, and the preview.

What is real: the FastAPI contract, including the SSE stream, stop, answer, diff, and artifacts. Project folders and git init. Tool calls for the shell, files, the package allow-list, build and test, preview, search, and load_skill. Spend cap, loop detection, the path guard, and refusal of supervisor tools for a normal agent. route_task assigns the only member.

What is not real yet: evals still always pass. The Docker network has no domain allow-list. Token counts are still ceil(chars/4). Older messages are truncated, not summarised. The mocked chat run does not take screenshots. The GitHub push and pull request path was not exercised against GitHub. The landing-page test that calls OpenAI runs only when RUN_REAL_LLM_TESTS=1.

## Why

The studio could show a run, and the run was a script. This session makes the same contract do the work, and leaves task assignment in one function so a supervisor can replace it later.

## How I tested

- `uv run --directory api pytest` — 10 passed, 1 skipped (the real OpenAI landing-page test)
- `pnpm typecheck` — pass
- `pnpm lint` — pass (the existing react-virtual and img warnings)
- `pnpm test` — 76 passed
- `pnpm test:e2e` — 12 passed on the mock studio, then 1 passed for chat against the API with the model mocked at the gateway. The chat spec creates an agent, creates a project, sends a message, and sees the summary and index.html.

## Screenshots

/chat lists projects and New project (name, agent, optional repo URL and token). /chat/[projectId] is the thread, a working card that expands into the live run, and a preview pane. DEV LOCAL MODE shows a yellow banner. A finished run adds an agent message with the summary, the files, and the preview link.

## New dependencies

- fastapi: the HTTP API
- uvicorn: serve it
- sqlalchemy and alembic: SQLite and the documents migration
- pydantic: request models via FastAPI
- httpx: the GitHub pull request call
- pyyaml: pasted OpenAPI specs
- python-dotenv: load api/.env
- openai: model calls, imported only in the gateway
- docker: the sandbox client when Docker answers
- pytest: the API tests

## Out of scope / follow-ups

Real evals, a Backend Engineer agent, and routing rules. Those replace route_task later. They are not in this PR.

## Session summary

Session: S6 feat/real-engine-chat
Built: The chat talks to FastAPI. A message creates a task, route_task assigns the project's only member, and a run works in a real folder on this machine. OpenAI is called through the gateway, tool calls are executed, and the thread shows the summary, the files, and the preview. The same task and agent shape can take a supervisor later.
Decisions: Amendment A was not in the repo; the session text is the spec. One SQLite documents table holds the records. The event stream is a poll of that table, so resume does not depend on a live socket. route_task is the only place a task is assigned. DEV LOCAL MODE runs commands in the project folder when Docker does not answer. The OpenAI key stays in api/.env. Model tags moved to the API. Mocks stay on for the web unit tests and the studio browser tests.
Failures / known gaps: Evals still always pass. The Docker container does not enforce a domain allow-list. Token counts are still ceil(chars/4). Messages older than the last 20 are truncated, not summarised by a model. Screenshots are captured with Playwright when it is installed and the gateway is not mocked; the mocked chat run does not take them. The GitHub branch, push, and pull request path is implemented and was not exercised against GitHub. One run at a time is not enforced. Tool results are not wrapped as untrusted. The real landing-page test runs only when RUN_REAL_LLM_TESTS=1.
New dependencies: fastapi, uvicorn, sqlalchemy, alembic, pydantic, httpx, pyyaml, python-dotenv, and pytest for the API. openai is imported only in the gateway. docker is the sandbox client when Docker answers.
Follow-ups for the next session: Real evals. A Backend Engineer agent. Routing rules that replace route_task.
