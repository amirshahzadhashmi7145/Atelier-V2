## Summary

- Add a **provider protocol** under `api/gateway/providers/` and route all model traffic through the gateway facade (no SDK imports in runtime).
- **Gemini** via `google-genai`: model list filtering, family-based `configSchema`, streaming/tool mapping, and the same tool pairing checks as OpenAI.
- **Settings > Providers** Gemini card and **grouped model picker**; gateway **timeouts and retries** with `MODEL_RETRY` / “Retrying model” in chat.
- **Connect 4 hang (pre-fix):** runs called the **OpenAI** API with a **Gemini model id**, so the stream never completed reliably and the run appeared frozen until gateway timeouts and provider routing were added.
- **Gemini `thought_signature` (post-merge fix):** the adapter rebuilt assistant function-call turns from TOOL_CALLED events and dropped `thought_signature`; the transcript now stores verbatim `gemini_model_content` from the SDK stream and replays it on the next call. Missing storage raises `internal: thought_signature lost`; provider 4xx fails the run immediately with the API message.
- **Studio 400 on Connect 4 (`run_11317`):** the API process was started before this code and never reloaded, so the studio still sent reconstructed functionCall parts. Parallel same-name calls now keep one stored part each; OpenAI leftover config (`webSearch`, `structuredOutputs` with tools) is filtered/ignored so Gemini 3.8 does not get `response_mime_type=application/json` together with tools.
- **Connect 4 leftover studio bugs:** `lucide-react` was refused (not on the React allow-list); `ok stop the preview server` started a coding run (heuristic defaulted to task, and the "preiew" typo did not match); 15 file reads failed the run as "no progress". Preview-stop now replies without a run, reads/lists skip the stale-tool counter, and lucide/fnmatch are on the stack allow-list.

**Note:** `origin` was missing at push time and was re-added as `https://github.com/amirshahzadhashmi7145/Atelier-V2.git`.

## What is real vs not

| Real now | Not yet |
|----------|---------|
| Backend Engineer library template, Node stack, evals | Reviewer / team lead, PM, QA |
| Multi-member projects, overlap block, @mention | Live MCP/API tool dispatch |
| Scope/keyword/classifier routing and backend-first split | Anthropic adapter |
| `api/CONTRACT.md` handed to the frontend run | |

## Test plan

- [x] `cd api && GATEWAY_MOCK=1 .venv/bin/pytest -q` — 58 passed, 5 skipped/failed (eval loop + vite scaffold match main/local env)
- [x] `api/tests/test_gemini_provider.py` — fixture stream, `thought_signature` replay, parallel same-name calls, leftover config dropped, structuredOutputs ignored when tools present, provider 400 → failed run &lt;2s
- [x] Preview-stop does not create a run (`ok stop the preiew server`); 16 distinct file reads complete; `search_data` ×16 still fails "no progress"; lucide-react + `@tailwindcss/*` allowed
- [x] `RUN_REAL_LLM_TESTS=1` Connect 4 multiplayer + CPU difficulty on `gemini-3.8-flash` with **Record model requests** — completed in 5m36s; captures at `api/debug/runs/<run_id>/*.json` (gitignored)
- [ ] `cd web && pnpm exec playwright test tests/e2e/providers.spec.ts` (with dev server / MSW as in CI)

## New dependencies

none

## Session summary (S12)

Session: S12 feat/backend-engineer  
Built: A Backend Engineer can share a project with the Frontend Engineer. Routing sends work to the right member or splits it backend-first with an API contract file.  
Decisions: `@Backend`/`@Frontend` is the first token only; `package.json` and `tsconfig*` may overlap as read-only; shared writes are refused while the other member is working.  
Failures / known gaps: Real todo-app LLM run is gated; reviewer/PM/QA roles are out of scope. Pre-existing web typecheck errors on main are unchanged.  
New dependencies: none  
Follow-ups: Team Lead / reviewer; run the live todo-app test with `RUN_REAL_LLM_TESTS=1`.
