## Summary

- Persist an OpenAI-style run **transcript** (assistant `tool_calls` + `tool` results) so every model turn sees prior tool output; trim drops whole call/result groups only.
- **Gateway pairing assert** before each call; violations fail the run with `internal: tool result missing`.
- **Settings > Runs > Advanced**: `recordModelRequests` writes redacted JSON to `api/debug/runs/<runId>/<callIndex>.json` (gitignored).
- Richer **tool result text** (files read/list caps, load_skill, build_test tail) and **vite-react-ts** local starter that `npm run build` can use.
- Loop stop names **identical read-only repeats** as a possible pairing bug and links to capture when enabled.

**Root cause (one sentence):** The run loop logged tool events to SSE/DB but never appended `tool` messages to the model context, so the model repeated reads without ever “seeing” results.

## How I tested

```bash
uv run --directory api pytest tests/test_tool_pairing.py tests/test_tool_results.py tests/test_gateway_capture.py tests/test_run_transcript_integration.py tests/test_engine.py -q
```

Mock Connect 4 run with capture on (`GATEWAY_MOCK=1`, `recordModelRequests: true`): run completed after read → write with paired messages in capture file `2.json`.

### Capture evidence (redacted)

**First request (`0.json`):** system + user task only — no prior tool turns.

**Later request (`2.json`, excerpt):** assistant `files` read → tool message with `package.json` body → assistant `files` write → tool `wrote (changed=True)`.

## New dependencies

None.

## Out of scope

Responses API / reasoning-model path (placeholder test only; gateway remains Chat Completions).
