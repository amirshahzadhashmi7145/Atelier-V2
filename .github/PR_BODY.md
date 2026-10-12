## What

The Agents editor, on an empty studio. A user imports the Frontend Engineer from the library or starts blank, picks a model, edits the prompt, adds evals, saves a version, and sets it active after the evals pass. Settings > Providers stores an OpenAI key by reference and refreshes the model list.

## Why

Agents, skills, and stacks are user data, not a fixture. Model settings have to come from the provider schema so a new option does not need a code change. Set active stays locked until the evals the user wrote have passed.

## How I tested

- `pnpm typecheck` — pass
- `pnpm lint` — pass
- `pnpm test` — 44 passed
- `pnpm test:e2e` — 7 passed (axe on Agents, Tools, Skills, Runs, Providers, and the editor; the editor flow imports the Frontend Engineer, sets reasoning effort and web search, saves a version, runs evals, sets active, and diffs two versions)
- In the browser at http://127.0.0.1:3000: New agent shows the library, import opens the editor with the prompt, access checklists, the Buildable UI eval, compiled preview, and Set active disabled until evals pass

## Screenshots

Agents starts empty, with New agent. After import, the editor shows Identity, Model (schema form and "no stats entered"), Prompt with a compiled preview, Access, and Evals. Set active stays disabled until Run evals. The versions drawer shows the role diff.

## New dependencies

- react-hook-form: forms for a blank agent, an eval, and the provider key
- zod: validate those forms
- @codemirror/view, @codemirror/state, @codemirror/lang-markdown, @codemirror/commands: the five prompt editors
- @codemirror/language: required by the markdown mode
- @codemirror/merge: read-only diff in the versions drawer

## Out of scope / follow-ups

Tool tabs, the skills editor, and the runs UI. The provider test does not call OpenAI. The mock eval runner always passes. Next session is the tools registry.

## Session summary

Session: S2 feat/agents-editor
Built: The studio starts empty. The user imports the Frontend Engineer from the library or creates a blank agent, then edits identity, a model settings form rendered from configSchema, budgets, five prompt editors with a compiled preview, access checklists, and evals. Settings > Providers stores an OpenAI key by reference, tests the connection, and caches six mock models for an hour. Set active stays disabled until every eval on the latest version has passed. The versions drawer diffs two prompts in a read-only merge view.
Decisions: Library templates stay in roles/, skills/, and stacks/ and are copied in on import, including the skills and stacks an agent names. Model prices and benchmarks stay empty so the card says "no stats entered" until a human adds a sourced number. The six mock models differ by which settings their schema includes. Control tools are omitted from GET /tools and always appended at compile time. Eval runs in the mock always pass; the real runner is S9. The mock store is remembered in sessionStorage so a client navigation does not wipe the agent the user just imported. react-hook-form and zod validate the blank agent, the eval, and the provider key. CodeMirror is loaded when the editor mounts; the merge view is loaded only when the versions drawer opens.
Failures / known gaps: The provider test does not call OpenAI; any stored key counts as connected. Zip import, tool tabs, the skills editor, and the runs UI are unchanged. Test run queues a mock run and does not open a live view. A full browser reload keeps the mock data for the tab, and the API key itself is dropped because it is not stored in the page.
New dependencies: react-hook-form: forms for a new agent, an eval, and the provider key. zod: validate those forms. @codemirror/view, @codemirror/state, @codemirror/lang-markdown, @codemirror/commands: the five prompt editors. @codemirror/merge: read-only version diff. @codemirror/language: required by the markdown mode.
Follow-ups for the next session: Tools page tabs, MCP discover, and API import against the same mock. Control tools stay off that page.
