## What

The Agent Studio contract and the first studio shell. `openapi/agent-studio.yaml` is the API. The Next.js app generates a client from it and serves agents, tools, skills, and runs from an in-memory mock seeded by the Frontend Engineer role.

## Why

Later sessions build the editor, the registry, and the runtime against this contract. Starting from the spec and a mock means those pages do not invent a second set of types.

## How I tested

- `pnpm typecheck` — pass
- `pnpm lint` — pass
- `pnpm test` — 30 passed
- `pnpm test:e2e` — 5 passed (four pages with axe, plus nav from Agents to Tools)
- In the browser at http://127.0.0.1:3000/agents the Frontend Engineer card renders. Clicking Tools lists the eleven builtin tools with permission badges.

## Screenshots

Agents shows the Frontend Engineer card in the studio shell. Tools shows shell, files, package_install, build_test, headless_browser, preview_deploy, search_data, load_skill, complete, raise_clarification, and escalate, each with a permission badge.

## New dependencies

- @tanstack/react-query: server state
- zustand: theme and other UI state
- openapi-fetch: call the generated client
- openapi-typescript: generate types from the contract
- msw: mock the contract in the browser and in Vitest
- yaml: parse role, stack, and skill seed files, and imported API specs
- vitest, jsdom, @testing-library/react, @testing-library/jest-dom: unit and component tests
- @vitejs/plugin-react: transform JSX in Vitest
- @playwright/test, @axe-core/playwright: end-to-end tests with axe
- @base-ui/react, class-variance-authority, cn, tw-animate-css, sonner, lucide-react: shadcn/ui

## Out of scope / follow-ups

No agent editor, tool tabs, skill import UI, live run view, FastAPI, or runtime. The mock can stream a fake run; the UI does not read it yet. `models.json` is empty until model cards are listed. Next session is the Agents editor.

## Session summary

Session: S1 feat/contract-scaffold
Built: The monorepo now has the OpenAPI contract, a generated client, and an MSW store seeded from the Frontend Engineer role, four skills, the React and Next.js stacks, and three past runs. The studio shell lists agents, tools, skills, and runs against that mock, with loading, empty, and error states.
Decisions: Next.js 16.4.0 is the latest patched 16.x. Mocks stay on unless NEXT_PUBLIC_USE_MOCKS=false, so the app runs without an env file. models.json is empty because this session did not list model cards; the seed agent names gpt-5 and leaves fit lines and benchmarks unset. Eleven builtin tools are seeded because the runtime control set adds complete, raise_clarification, and escalate to the eight domain tools. The fourth starter skill is definition-of-done. The Frontend Engineer starts with React only. React docs are pinned to commit 046f17d04295ba047bb5739026b4ac3110f17028; Next.js docs are pinned to the v16.4.0 GitHub tree until the sandbox can read next/dist/docs. The web compiler counts tokens as ceil(chars/4). Theme lives in zustand. Contract drift in CI is the generated client and the seed JSON, because there is no FastAPI app to diff until S7. Studio routes set instant = false so Next.js does not drop the client lists during its instant-navigation check.
Failures / known gaps: No agent editor, tool tabs, skill import UI, or live run view. The mock can stream about 25 events over 30 seconds, including one client-tool request and one refused package, but the UI does not read that stream yet. Zip import does not unpack the archive. Importing an API by URL returns one canned operation. GET /models is empty. No FastAPI, database, or runtime.
New dependencies: @tanstack/react-query: server state. zustand: theme and other UI state. openapi-fetch and openapi-typescript: generated client. msw: mock the contract. yaml: parse seed files and API specs. vitest, jsdom, Testing Library: unit and component tests. @vitejs/plugin-react: JSX in Vitest. Playwright and axe: end-to-end tests. shadcn/ui packages: the required UI kit.
Follow-ups for the next session: Agents page editor, five prompt editors, debounced compile preview, Access card, versions drawer, and Set active disabled until a smoke eval passes.
