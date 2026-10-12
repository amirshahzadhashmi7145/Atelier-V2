## What

A run can be started, watched live, stopped, answered, and reviewed against the mock stream. The new-run form, the three-pane live view, and the runs list all read the same contract.

## Why

This is the screen that shows the studio works: one agent, one task, and a stream of what it did. The backend session has to implement this stream, not invent a second one.

## How I tested

- `pnpm typecheck` — pass
- `pnpm lint` — pass (warnings only: react-virtual cannot be memoized, and screenshot `img` tags stay native because the urls are data urls)
- `pnpm test` — 76 passed
- `pnpm test:e2e` — 12 passed. The new spec starts a run from the form, sees events, answers the clarification, responds to the client tool, reloads without a duplicate row, and opens the summary and the diff. A second run is cancelled within 2 seconds. Axe is clean on /runs, /runs/new, and the live run.
- In the browser at http://127.0.0.1:3000, that same path was clicked through: Test run lands on the form with the eval task, Start run opens the live log, Respond and Send answer resume it, and the summary names the three diff files.

## Screenshots

/runs/new shows the agent, the scaffold from its stacks, the task, criteria rows, and the spend cap with a Settings link. /runs/[id] is the activity log, the diff, and the status card with the spend bar. A finished run replaces the status card with the summary, Open PR, Download zip, Open preview, and Re-run with changes.

## New dependencies

- `@tanstack/react-virtual`: virtualize the activity log, one row per event.

## Out of scope / follow-ups

No backend and no sandbox. Eval runs in the mock still always pass. A spec URL without a pasted document is refused. Loop detection is stored and not enforced. Attachments are ids only.

## Session summary

Session: S5 feat/runs-ui
Built: A run can be started, watched, stopped, answered, and reviewed against the mock stream. /runs/new picks an agent (and blocks when it has no active prompt), a GitHub repo or a scaffold from that agent's stacks, a task, criteria, and attachments. The spend cap is read-only and links to Settings. /runs/[id] is three resizable panes: an activity log, the diff / logs / screenshots / preview, and a status card with the spend bar. A client-tool card and a clarification card sit above the status while the run is waiting. A finished run shows the summary and links to the PR, the zip, the preview, and a re-run. /runs lists runs with agent and state filters. Test run on the agent editor opens the form with the latest eval filled in.
Decisions: Amendment A was not in the repo; the session text is the spec. Run and RunCreate no longer have a budget field. The spend cap is Settings > Runs. The log subscribes to the query cache; the SSE hook is the only reader of the stream. The mock keeps a script cursor in sessionStorage and resumes a non-terminal run after a full page load. Attachments are stored as ids (file names and links).
Failures / known gaps: No backend and no sandbox. Eval runs in the mock still always pass. A spec URL without a pasted document is refused. Loop detection is stored and not enforced.
Contract the backend must implement exactly as mocked: SSE frames are `id: <seq>`, `event: <type>`, `data: <Event JSON>`, separated by a blank line. `GET /runs/{id}/events?after=<seq>` omits events with seq less than or equal to that value. Event types are RUN_STARTED, MODEL_CALLED (with cost: inputTokens, outputTokens, usd), TOOL_CALLED, TOOL_RESULT, TOOL_REFUSED, SKILL_LOADED, CLIENT_TOOL_REQUESTED, CLARIFICATION_RAISED, STATE_CHANGED, RUN_COMPLETED, and RUN_FAILED. CLIENT_TOOL_REQUESTED sets status waiting_client and pauses until `POST /runs/{id}/client-tool-result` with requestId. CLARIFICATION_RAISED sets status waiting_user and pauses until `POST /runs/{id}/answer` with text; the run then returns to running. `POST /runs/{id}/stop` sets status cancelled, appends STATE_CHANGED, and the event stream ends within 2 seconds. RUN_COMPLETED carries the RunSummary plus prUrl, previewUrl, and branch. RUN_FAILED carries cause and text. `GET /runs/{id}/diff` returns three files (path, before, after). `GET /runs/{id}/artifacts` returns screenshots (one url per viewport), a build log, a test log, a zip url, and a preview. Run has no budget field.
New dependencies: @tanstack/react-virtual, so the activity log virtualizes one row per event.
Follow-ups for the next session: The backend that implements this contract.
