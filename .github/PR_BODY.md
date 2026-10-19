**Note:** `origin` was missing at push time and was re-added as `https://github.com/amirshahzadhashmi7145/Atelier-V2.git`.

## What

LiteLLM is now the single live model layer for every agent of every role. Provider keys are data (OpenAI and Gemini to start): add, test, and remove them in Settings, stored encrypted, returned only as a masked hint. Tool-calling models are listed per provider. Every call records cost on the run, the agent, and the role, and spend caps use that figure. The architecture decision record is in `docs/adr/ARCHITECTURE-DECISION.md`.

## Why

Session 14, step 1 of the ready-made-parts plan. Roles stay data; workers and stacked supervisors share one gateway that does not know roles. Direct OpenAI SDK calls are gone from production complete/stream/list.

## How I tested

- `cd api && GATEWAY_MOCK=1 uv run pytest -q tests/test_s14_litellm.py` — 9 passed (routing, worker=supervisor gateway, key masking / no key on disk or in API/logs, tool-calling filter, cost per run/agent/role, spend cap from recorded cost, role-fit storage, no `from openai import` in app/gateway/runtime/store)
- `cd api && GATEWAY_MOCK=1 uv run pytest -q` — 103 passed, 6 skipped, 1 failed (`test_tic_tac_toe_ui_reaches_a_built_app_with_screenshots` PNG size, pre-existing flake; not worse)
- `cd web && pnpm gen:api && pnpm typecheck && pnpm test` — typecheck clean, 80 Vitest tests passed
- Real provider calls stay behind `RUN_REAL_LLM_TESTS=1`

## Screenshots

Settings > Providers: API key field, Save / Remove / Test / Refresh per provider card (OpenAI and Gemini from data). After save the UI shows a masked hint, never the key.

## New dependencies

- `litellm==1.83.0` — open-source model gateway. **Do not use 1.82.7 or 1.82.8** (March 2026 PyPI supply-chain compromise). 1.83.0 is the first release after LiteLLM CI/CD v2 and is the pin recorded in the ADR.
- `cryptography>=44` (resolved 50.0.2) — Fernet encryption for provider keys at rest under `PROJECTS_DIR/.secrets/` (gitignore already has `.secrets/`)

## Out of scope / follow-ups

OpenHands workers, LangGraph supervisors, QA role, MCP wrapper, memory, model suggestion badges, fallback models, automation (plan approval / two-rework user decide become escalation-only). Gemini thought-signature unit tests still go through `gateway/providers/gemini.py` (`google.genai`); live runtime complete/stream goes through LiteLLM.

## Hardcoded role spots (not refactored this session)

Logic, not tests/fixtures:

- `api/runtime/route_task.py` — frontend/backend keyword split and classifier words `frontend` / `backend` / `both`
- `api/runtime/lead.py` — supervisor detection includes the string `team-lead`
- `api/runtime/loop.py` — `CONTRACT.md` injection and write path gated on `roleKey` containing `backend`
- `api/runtime/members.py` — colour map keyed by `frontend`, `frontend-engineer`, `backend`, `backend-engineer`, `team-lead`
- `api/gateway/mock_turns.py` — default plan picks members whose role/name contains `frontend` / `backend`
- `web/src/lib/models/tags.ts` — tag enum includes `frontend`, `backend`, `qa`

## What is real vs not

| Real now | Not yet |
|----------|---------|
| One LiteLLM gateway for live calls; mock scripts unchanged | OpenHands for workers |
| Settings add/test/remove OpenAI and Gemini keys; encrypted at rest; masked hint only | Other providers in the UI (list is data; add a provider row later) |
| Tool-calling model list grouped by provider | Suggestion badge / role-fit ranking |
| Cost on run + agent-spend + role-spend; spend cap uses recorded usd | LangGraph supervisors, QA, PM |
| Role-fit label storage keyed by role id | Automation: escalation-only plan/rework |

## Session summary (S14)

Session: S14 feat/s14-litellm-gateway
Built: LiteLLM 1.83.0 as the only live model layer; encrypted provider keys in Settings; tool-calling model catalog; cost ledger; ADR for generic roles and minimal human input.
Decisions: Pin 1.83.0 (never 1.82.7/1.82.8). Gateway takes model, messages, tools, run id — not a role. Provider list is seed data. Keys never logged or returned after save.
Failures / known gaps: Gemini adapter still used by thought-signature tests. Tic-tac-toe PNG flake unchanged. Suggestion engine and later commodity layers not started.
New dependencies: litellm==1.83.0, cryptography
Follow-ups: OpenHands, LangGraph, MCP wrapper, memory, suggestions, automation.
