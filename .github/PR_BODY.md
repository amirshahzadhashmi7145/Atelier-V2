## Summary

- Add a **provider protocol** under `api/gateway/providers/` and route all model traffic through the gateway facade (no SDK imports in runtime).
- **Gemini** via `google-genai`: model list filtering, family-based `configSchema`, streaming/tool mapping, and the same tool pairing checks as OpenAI.
- **Settings > Providers** Gemini card and **grouped model picker**; gateway **timeouts and retries** with `MODEL_RETRY` / “Retrying model” in chat.
- **Connect 4 hang (pre-fix):** runs called the **OpenAI** API with a **Gemini model id**, so the stream never completed reliably and the run appeared frozen until gateway timeouts and provider routing were added.
- **Gemini `thought_signature` (post-merge fix):** the adapter rebuilt assistant function-call turns from TOOL_CALLED events and dropped `thought_signature`; the transcript now stores verbatim `gemini_model_content` from the SDK stream and replays it on the next call. Missing storage raises `internal: thought_signature lost`; provider 4xx fails the run immediately with the API message.
- **Studio 400 on Connect 4 (`run_11317`):** the API process was started before this code and never reloaded, so the studio still sent reconstructed functionCall parts. Parallel same-name calls now keep one stored part each; OpenAI leftover config (`webSearch`, `structuredOutputs` with tools) is filtered/ignored so Gemini 3.8 does not get `response_mime_type=application/json` together with tools.

**Note:** `origin` was missing at session start and was re-added as `https://github.com/amirshahzad-hashmi7145/Atelier-V2.git`.

## What is real vs not

| Real now | Not yet |
|----------|---------|
| OpenAI + Gemini providers, env keys, test/refresh, grouped picker | Anthropic adapter |
| Gateway timeouts/retries, pairing on both paths | Ollama as first-class `google-genai`-style adapter (still OpenAI-compatible) |
| Recorded Gemini fixture + pytest coverage | Backend Engineer role |

## Test plan

- [x] `cd api && GATEWAY_MOCK=1 .venv/bin/pytest -q` — 58 passed, 5 skipped/failed (eval loop + vite scaffold match main/local env)
- [x] `api/tests/test_gemini_provider.py` — fixture stream, `thought_signature` replay, parallel same-name calls, leftover config dropped, structuredOutputs ignored when tools present, provider 400 → failed run &lt;2s
- [x] `RUN_REAL_LLM_TESTS=1` Connect 4 multiplayer + CPU difficulty on `gemini-3.8-flash` with **Record model requests** — completed in 5m36s; captures at `api/debug/runs/<run_id>/*.json` (gitignored)
- [ ] `cd web && pnpm exec playwright test tests/e2e/providers.spec.ts` (with dev server / MSW as in CI)

## New dependencies

- **google-genai** — Gemini SDK, confined to `api/gateway/providers/gemini.py`

## Session summary (S11)

Session: S11 feat/gemini-provider  
Built: Provider-based gateway with Gemini parity, provider settings UI, grouped model picker, and timeout/retry behaviour so hung model calls cannot freeze a run indefinitely.  
Decisions: Explicit `agent.model.provider` drives routing; default model spec prefers Gemini only when OpenAI key is absent.  
Failures / known gaps: Anthropic/Ollama adapters deferred; eval/scaffold pytest failures pre-existing on main in this environment.  
New dependencies: google-genai  
Follow-ups: Anthropic/Ollama providers; Backend Engineer; eval loop investigation on main.
