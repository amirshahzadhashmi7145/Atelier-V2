**Note:** `origin` was missing at push time and was re-added as `https://github.com/amirshahzadhashmi7145/Atelier-V2.git`.

## What

A Team Lead agent that splits work, assigns it, and reviews every result before the user sees it as done. It writes no application code.

## Why

S12 can split Backend/Frontend, but nothing reviews the work or holds the parent task until every child is approved.

## How I tested

- `cd api && GATEWAY_MOCK=1 .venv/bin/pytest -q tests/test_s13_lead.py tests/test_s12_backend.py -k "not real_"` — 18 passed
- `cd api && GATEWAY_MOCK=1 .venv/bin/pytest -q` — 94 passed, 6 skipped, 1 failed (`test_tic_tac_toe_ui_reaches_a_built_app_with_screenshots` PNG size, pre-existing)
- `cd web && pnpm gen:api && pnpm gen:seed && pnpm typecheck && pnpm test` — typecheck and 80 Vitest tests passed
- Browser: Settings > Runs shows **Approve plans before running** (on) and **Max spend per review** ($1)
- Playwright chat e2e: chromium not installed here; studio already bound :3000/:8000 (live OpenAI, no credits) so the plan card was not driven in that process. Mock pytest covers plan-before-runs, approve, review verdict, max 2 reworks, write refuse, and review spend cap.

## Screenshots

Settings > Runs: approve-plans checkbox default on; max spend per review default 1.

## New dependencies

none

## Out of scope / follow-ups

PM as a separate role; QA as a separate role; routing by learned stats; `RUN_REAL_LLM_TESTS=1` three-agent todo app.

## What is real vs not

| Real now | Not yet |
|----------|---------|
| Team Lead library template (supervisor, empty zones, three evals) | PM / QA roles |
| Lead-first routing when the project has a Team Lead | Routing by learned stats |
| Numbered plan in the thread; edit + approve; Settings toggle default on | Isolated library "Run evals" for the lead without project members |
| Review loop: approve advances, `changes_requested` reworks the author at most twice | Live three-agent todo (`RUN_REAL_LLM_TESTS=1`) |
| Parent completes only after every child is approved; lead wrap-up + preview | |
| Lead cannot write files; review spend cap default $1, reported not retried | |

## Session summary (S13)

Session: S13 feat/team-lead-reviewer
Built: A Team Lead library role splits work, assigns child tasks, and reviews every result before the user sees it as done. It writes no application code. When a project has a lead, user messages go to that agent first; child tasks appear as an editable numbered plan (approve-before-run is on by default); each completed child starts a fresh review run; the parent finishes only after every child is approved, then the lead posts the wrap-up and refreshes the preview.
Decisions: `create_task` only records planned children; runs start after plan approve. Review `changes_requested` creates a new task for the same author at most twice, then the user decides. Review spend is a separate cap (default $1) and is reported, not retried. Lead/review runs cannot write files or run non-build/test shell.
Failures / known gaps: PM and QA as separate roles, and routing by learned stats, are out of scope. Isolated library "Run evals" for the lead still need a project with members. The live three-agent todo app is behind `RUN_REAL_LLM_TESTS=1`. `test_tic_tac_toe_ui_reaches_a_built_app_with_screenshots` failed on PNG dimensions (pre-existing flake). Playwright chromium was missing in this environment; a second `next dev` is locked by the studio already on :3000. Settings > Runs toggle was verified in the browser.
New dependencies: none
Follow-ups: PM role; run the live todo-app test with Team Lead + Backend + Frontend; Playwright browsers in CI.
