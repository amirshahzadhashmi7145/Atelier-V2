## What

Skills, discovered OpenAI models, and the Tools page. A user creates or imports a skill, picks a model whose settings come from its family schema, and adds MCP tools, API operations, and data sources from the registry.

## Why

Nothing in the studio is a fixture. Skills and tools have to be added in the UI, and the model list has to be whatever the provider returns so a new model shows up without a code change.

## How I tested

- `pnpm typecheck` — pass
- `pnpm lint` — pass
- `pnpm test` — 63 passed
- `pnpm test:e2e` — 8 passed (axe on Agents, Tools, Skills, Runs, Providers, the agent editor, and the new skill page; the editor flow still imports the Frontend Engineer, sets reasoning effort and web search, saves, runs evals, and diffs; the new flow creates a skill, imports one from a URL, attaches it, switches a reasoning model for a non-reasoning one, imports two MCP tools and one API operation, and refreshes a data source)
- In the browser at http://127.0.0.1:3000: Tools shows the five tabs and seven built-in cards, Configure on files opens Allowed paths, Skills shows New skill and Import, Providers takes an API key in the page and Test connection sends it to OpenAI

## Screenshots

Tools opens on Built-in (shell through search_data) with a permission badge, a cost note, and Configure. Skills starts with New skill and Import. Providers has an API key field. The model menu uses dark text on a white list.

## New dependencies

None.

## Out of scope / follow-ups

Runs UI, the stacks sheet, and the backend. The API mock returns five canned operations for any spec. Zip archives that store sizes in a data descriptor are not unpacked. Next session can add stacks on the Access card.

## Session summary

Session: S3 feat/skills-models-tools
Built: Skills can be created in the editor or imported from a GitHub path, a zip, or a folder, with a review step and a diff when the same origin is imported again. Settings > Providers keeps the OpenAI key in this browser tab and lists the chat models OpenAI returns. The agent editor renders settings from each id's family schema. The Tools page has Built-in, Client-side, MCP, APIs, and Data; confirming a discovery or an import adds those tools, and a data source is one search_data tool.
Decisions: Model ids are never hardcoded. Reasoning families (o-series and gpt-5, except chat snapshots) get the documented reasoning_effort enum and no temperature; other gpt/chatgpt ids get temperature and maxOutputTokens; every chat model gets webSearch and structuredOutputs; anything else gets that base pair. The key stays in sessionStorage for this tab and is sent only on the models request. A failed discovery clears the cached catalog instead of leaving Connected. Select options use dark text on white so the menu stays readable in the dark theme. The mock returns one canned SKILL.md for any URL and five canned operations for any spec. Control tools stay off the Tools page. Prices and benchmarks stay empty.
Failures / known gaps: Zip entries that use a data descriptor are not unpacked. The API mock does not parse the pasted spec. The runs UI and the stacks sheet are not built. Eval runs in the mock still always pass.
New dependencies: none
Follow-ups for the next session: Stacks on the Access card, and a real spec parser when the API exists.
