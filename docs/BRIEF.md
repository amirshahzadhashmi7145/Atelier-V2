# Agent Studio: build brief (week 1)

## What we are building

A web app where a user defines AI agents (prompt sections, tools, skills, tech stacks, model), runs ONE agent on a task inside a sandbox, and watches the run live. Week 1 ships the studio (four pages), the runtime, and one working agent: the Frontend Engineer. Later roles (Backend, Team Lead, PM) are added through the same pages with no new code paths.

## Direction from S4

Budgets are not an agent setting. Settings > Runs holds the platform cap (max spend, default $5) and the advanced bounds. The OpenAI key stays in `web/.env.local`; the Providers page only says whether it was found. Model tags and a one-line note live in `web/data/model-tags.json` until the backend exists. Stacks are created in the UI or imported from the library. Nothing is installed until then.

## Direction from S3

Skills are created or imported in the UI (GitHub path, zip, or folder). Re-import of the same origin returns a diff before it is saved. Model ids come from OpenAI's models list (`OPENAI_API_KEY` in `.env.local`, server-only); `configSchema` is chosen by family pattern, never by a hardcoded name list. The Tools page is the five tabs. Control tools stay hidden.

## Direction from S2

A fresh install has no agents, skills, or stacks. `roles/`, `skills/`, and `stacks/` are a library (`GET /library?kind=`, `POST /library/{id}/import`), not a seed. Models come from Settings > Providers. `AgentDefinition.model` is `{provider, name, config}` validated against the model's `configSchema`. Each agent has evals; results live on the prompt version; Set active requires every eval to pass. `complete`, `raise_clarification`, `escalate`, and `load_skill` are kind `control`: always on, hidden from Tools, not removable.

Order of work: contract first, UI against mocks, then the backend that implements the same contract, then the runtime. Each session below is one feature branch and one PR.

## Git workflow (mandatory, every session)

1. Never commit to main. Start every session with: git checkout main && git pull, then git checkout -b feat/<area>-<short-slug> (e.g. feat/agents-editor, feat/runs-sse).
2. One feature per branch. Small commits with conventional messages (feat:, fix:, test:, chore:).
3. When the session's exit tests pass, open a PR with the GitHub CLI: gh pr create --base main --title "<feat: ...>" --body-file .github/PR_BODY.md. The body must contain: What, Why, How I tested (commands + results), Screenshots (UI PRs), New dependencies (name + one-line reason), Out of scope / follow-ups.
4. Never merge, never force-push, never rebase a pushed branch. The human merges. After merge, the next session starts from a fresh main.
5. If a session cannot finish, still open the PR as Draft with what is done and what is not.

## Stack (do not substitute)

Frontend: Next.js 16 App Router (latest patched 16.x), React 19, TypeScript strict, Tailwind v4, shadcn/ui, lucide-react, @tanstack/react-query v5 (all server state), zustand v5 (UI state only), react-hook-form + zod, openapi-typescript + openapi-fetch (generated client), msw v2, CodeMirror 6 (@codemirror/lang-markdown; @codemirror/merge read-only for diffs, lazy-loaded), @tanstack/react-virtual, Vitest + Testing Library, Playwright + @axe-core/playwright.

Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite in dev / PostgreSQL in prod (same SQL subset), pydantic v2, httpx, openai SDK (ONLY inside gateway/), Docker SDK for the sandbox, pytest. uv for Python deps, pnpm for JS. Docker required on the host.

## Non-negotiable rules

1. Contract first. openapi/agent-studio.yaml is the source of truth for both sides. FastAPI routes are checked against it in CI (schemathesis or an openapi diff). No fetch() outside web/src/lib/api. Types are generated with `pnpm gen:api`, never hand-written.
2. Server state only in TanStack Query; zustand holds selected ids, panel sizes, theme, filters.
3. Every list has loading, empty and error states; every mutation has pending state and a failure toast.
4. No new dependency without a one-line reason in the PR body.
5. Never delete, skip or weaken a test to make a build pass.
6. Import boundaries enforced by lint: web: app -> features -> lib/components, features never import each other. api: orchestrator imports nothing from runtime; provider SDKs importable only in api/gateway/; DB sessions only in api/store/.
7. Tool access is enforced by the runtime against the agent's allow-list, never by prompt text. Enabled tech stacks are enforced by the package-install tool's allow-list and a pre-run task check, never by prompt text alone.
8. Secrets never enter model context or event payloads. Keys live in env/secret store; tools hold them.
9. Every state change in a run is an appended event. The UI is a reader of events.
10. End every session with the summary format at the bottom of this file, saved to docs/build-log.md and pasted in the PR body.

## Repository layout

See the week-1 session that opened the repo for the full tree. The contract lives at openapi/agent-studio.yaml. The web app is in web/. Seed inputs are roles/, skills/, stacks/, and api/models.json.

## Compile rule

web/src/features/agents/compile.ts and, later, api/runtime/compile.py must match. fixtures/compile-preview.json asserts the output.

"# Role" / "# Goal and definition of done" / "# How to work" / "# Constraints" / "# Output" from sections, then generated: "# Enabled stacks" (name + version per enabled stack, plus "Do not use or propose any other framework. If the task requires one, call raise_clarification."), "# Tools" (name: description per allowed tool), "# Skills" (name: description per attached skill, plus "Call load_skill(name) before using a skill.").

tokenCount = ceil(chars/4) in the mock; real tokenizer count in the API.

## Sessions

S1 feat/contract-scaffold: monorepo, openapi/agent-studio.yaml complete, generated client, MSW with seed data, studio layout + nav, CI (lint, typecheck, tests, openapi diff).

S2 feat/agents-editor: Agents page complete incl. versions drawer, compile preview, Access card.

S3 feat/tools-registry: Tools page, all five tabs, MCP discover and API import against mocks, Data sources table with refresh button.

S4 feat/skills: Skills page, import from repo path with preview and re-import diff, seed the four starter skills + react-best-practices import.

S5 feat/stacks-models: Stacks section on Access card, stacks/*.yaml, generated stacks section in compile, Models endpoint + ModelCard + fit lines, pre-run stack check (mocked).

S6 feat/runs-ui: Runs pages with SSE hook, virtualised log, merge-view diff, screenshots, preview, status card, stop, client-tool and clarification answer boxes.

S7 feat/api-core: FastAPI app implementing the contract for agents, tools, skills, stacks, models, runs (no runtime yet); Alembic; contract tests; web switched to real API.

S8 feat/runtime-sandbox: DockerSandbox, builtin tools, gateway (OpenAI), agent loop, orchestrator state machine, SSE, PR/zip output; Frontend Engineer v1 seeded from roles/frontend-engineer.yaml; the three fixture tasks run end to end.

S9 feat/smoke-eval: smoke eval runner over the three fixture tasks; result stored on the prompt version; Set active unlocked; ownStats in /models.

## Definition of done (every session)

pnpm typecheck && pnpm lint && pnpm test && pnpm test:e2e green (web); uv run pytest green (api, from S7); openapi diff clean; PR opened with the body template; build-log entry added.

## Runtime rules that are not in the OpenAPI file

Tool access is enforced against the agent's allow-list. Enabled stacks are enforced by the package-install allow-list (the union of enabled stacks) and a pre-run scan of the task for framework names that are not enabled: angular, vue, svelte, solid, remix, astro, nuxt. A hit puts the run in waiting_user with the question "This task mentions <X>, which is not enabled for this agent. Enable it or rephrase?".

Control tools are always present: complete(summary), raise_clarification(question), escalate(reason), load_skill(name). Loop detection: rolling hash of the last 8 tool calls; 3 identical or 2 consecutive no-change diffs fails the run with cause loop. Untrusted tool results are wrapped {source, trust:'untrusted', content}. Secrets never enter model context or event payloads. Every state change is an appended event. One run at a time. Stop ends within 10 seconds.

A benchmark entry requires a sourceUrl. Do not invent numbers. Seed model cards only from models the human lists; until then benchmarks is [] and fitLine is null.

## Session summary format

Append to docs/build-log.md and paste in the PR body:

Session: <id and branch>
Built: <what exists now, in two or three sentences>
Decisions: <choices made and why, one line each>
Failures / known gaps: <what does not work, honestly>
New dependencies: <name: reason>
Follow-ups for the next session: <list>

The HTTP contract, domain fields, stack allow-lists, event names, and runtime rules are implemented in openapi/agent-studio.yaml and the seed files. Do not invent a second copy of those lists in prose; read the spec file.
