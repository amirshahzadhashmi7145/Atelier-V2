## Summary

- Add a **provider protocol** under `api/gateway/providers/` and route all model traffic through the gateway facade (no SDK imports in runtime).
- **Gemini** via `google-genai`: model list filtering, family-based `configSchema`, streaming/tool mapping, and the same tool pairing checks as OpenAI.
- **Settings > Providers** Gemini card and **grouped model picker**; gateway **timeouts and retries** with `MODEL_RETRY` / “Retrying model” in chat.
- **Connect 4 hang (pre-fix):** runs called the **OpenAI** API with a **Gemini model id**, so the stream never completed reliably and the run appeared frozen until gateway timeouts and provider routing were added.

**Note:** `origin` was missing at session start and was re-added as `https://github.com/amirshahzad-hashmi7145/Atelier-V2.git`.

## What is real vs not

| Real now | Not yet |
|----------|---------|
| OpenAI + Gemini providers, env keys, test/refresh, grouped picker | Anthropic adapter |
| Gateway timeouts/retries, pairing on both paths | Ollama as first-class `google-genai`-style adapter (still OpenAI-compatible) |
| Recorded Gemini fixture + pytest coverage | Backend Engineer role |

## Test plan

- [x] `cd api && GATEWAY_MOCK=1 .venv/bin/pytest -q` — 58 passed, 5 skipped/failed (eval loop + vite scaffold match main/local env)
- [x] `api/tests/test_gemini_provider.py` — fixture stream, pairing, config_schema, list filter, timeout mock
- [ ] `cd web && pnpm exec playwright test tests/e2e/providers.spec.ts` (with dev server / MSW as in CI)
- [ ] Optional: `RUN_REAL_LLM_TESTS=1` Gemini tic-tac-toe test with `GEMINI_API_KEY`

## New dependencies

- **google-genai** — Gemini SDK, confined to `api/gateway/providers/gemini.py`

## Session summary (S11)

Session: S11 feat/gemini-provider  
Built: Provider-based gateway with Gemini parity, provider settings UI, grouped model picker, and timeout/retry behaviour so hung model calls cannot freeze a run indefinitely.  
Decisions: Explicit `agent.model.provider` drives routing; default model spec prefers Gemini only when OpenAI key is absent.  
Failures / known gaps: Anthropic/Ollama adapters deferred; eval/scaffold pytest failures pre-existing on main in this environment.  
New dependencies: google-genai  
Follow-ups: Anthropic/Ollama providers; Backend Engineer; eval loop investigation on main.
