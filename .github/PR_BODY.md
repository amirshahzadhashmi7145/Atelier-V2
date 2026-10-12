## What

Finish the S3 settings gaps and add stacks. Agents no longer have budgets. Settings > Runs holds the platform spend cap. The OpenAI key stays in `.env.local`. Settings > Models stores tags and a note. Stacks are created or imported, and they show up in the compiled preview.

## Why

Spend and safety bounds are platform settings, not something each agent edits. Model choice needs tags and the user's own run history. A stack should exist only after someone creates it or imports it.

## How I tested

- `pnpm typecheck` — pass
- `pnpm lint` — pass
- `pnpm test` — 69 passed
- `pnpm test:e2e` — 9 passed (axe on the studio pages, the agent editor, skills and tools, and Settings > Runs; the new flow checks the spend cap, the missing budget fields, a model tag chip, a created stack in the preview, and Import React)
- In the browser at http://127.0.0.1:3000: Settings > Runs shows Max spend per run at 5. The Frontend Engineer editor has New stack and Import React, and no Max iterations field.

## Screenshots

Settings > Runs shows one spend field and an Advanced disclosure. The agent Access card has New stack, Import React, and Import Next.js. The compiled preview includes `# Enabled stacks`.

## New dependencies

None.

## Out of scope / follow-ups

The runs UI and the backend. A spec URL without a pasted document is refused. Loop detection is stored and not enforced until the runtime.

## Session summary

Session: S4 feat/finish-s3-settings-stacks
Built: Budgets left the agent editor. Settings > Runs holds a visible spend cap and advanced bounds. The OpenAI key is read from .env.local again, and Providers only says whether it was found. Settings > Models stores tags and a note in a local JSON file, and the model picker shows those tags plus run stats. Stacks are created on the Access card or imported from the library, and enabled stacks show up in the compiled preview.
Decisions: S3 was still unmerged, so this branch starts from feat/skills-models-tools. Amendment A was not in the repo; the session text is the spec. Reasoning families seed planning and review; mini, nano, and fast seed cheap and fast; a saved tag replaces the guess. ownStats counts completed runs that have a summary. A data-descriptor zip is read from the central-directory size. A pasted OpenAPI document is parsed from its paths. Run records still keep a token ceiling because the visible cap is spend.
Failures / known gaps: The runs page is not built. There is no backend, so tags live in web/data/model-tags.json. A spec URL without a pasted document is refused. Eval runs in the mock still always pass. Loop detection is stored and not enforced until the runtime.
New dependencies: none
Follow-ups for the next session: The runs UI.
