## Summary

- Persist an OpenAI-style run **transcript** (assistant `tool_calls` + `tool` results) so every model turn sees prior tool output; trim drops whole call/result groups only.
- **Gateway pairing assert** before each call; violations fail the run with `internal: tool result missing`.
- **Settings > Runs > Advanced**: `recordModelRequests` writes redacted JSON to `api/debug/runs/<runId>/<callIndex>.json` (gitignored).
- One active run per project with queued follow-ups, edit-not-rewrite guards, auto build, daily spend cap, chat classifier, Teach sheet, and live streaming model output.

**Root cause (S10):** The run loop logged tool events to SSE/DB but never appended `tool` messages to the model context, so the model repeated reads without ever “seeing” results.

## How I tested

```bash
uv run --directory api pytest -q
cd web && pnpm typecheck && pnpm test
```

## New dependencies

None.

## Out of scope

Responses API / reasoning-model path. Backend Engineer, routing rules, supervisors.
