## Summary
- One active run per project: extra in-scope messages queue with a thread note; stop/wait/cancel/hold on stops the active run and clears the queue.
- Follow-ups (complete it, fix it, …) reuse prior task context; chat uses project summary, last five messages, and states what a run can do.
- Files tool prefers edit/append; full rewrites nudge then fail; auto build after three writes; complete requires a passing build when package.json exists.
- Zones limit writes only; untracked files appear in diffs; load_skill is once per run; skills over 8k tokens refused at save; model timeout with retry events; no-progress and daily spend caps.
- Chat composer shows agent is working with Stop; Access card warns when build/shell/preview tools are missing.

## Test plan
- [x] `api/.venv/bin/pytest` (45 passed, 2 skipped)
- [x] `cd web && pnpm typecheck && pnpm test` (80 passed)
- [ ] `cd web && pnpm test:e2e` (chat config; kills ports 3000/8000)

## New dependencies
None.

## Out of scope
Backend Engineer, routing rules, supervisors. `route_task` still assigns the only member.

Session: S9 feat/run-serialisation-loop-fixes
Built: Projects serialise runs, queue follow-up tasks, enforce edit-not-rewrite and build-before-complete, and surface clearer failures. The Frontend Engineer template zones and library tools match the vite scaffold. Settings add a per-project daily spend cap.
Decisions: Queued runs stay in `queued` status until `project_runs.drain` starts the next worker. Control messages skip task creation. Complete-time build/screenshot/preview runs only for project chat runs, not throwaway eval folders. Model timeouts use `MODEL_RETRY` events and mock hang via `MOCK_MODEL_HANG`.
Failures / known gaps: No git remote is configured locally; push uses the explicit GitHub URL. `GITHUB_TOKEN` in api/.env is still empty, so the live GitHub integration test is skipped. Live OpenAI model timeouts use mock hang in CI; production streaming timeout/backoff is not fully wired on the live OpenAI stream path. Playwright e2e was not re-run in this session after the last UI edits.
Follow-ups for the next session: Put a GitHub token in api/.env and run `RUN_GITHUB_TESTS=1`. Wire first-token timeout on the live OpenAI stream. Backend Engineer and routing rules.
