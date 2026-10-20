## Summary
- **Part 1 (real OpenHands run) did not run.** Docker is up. The Settings encrypted store (`~/.atelier-projects/.secrets/providers`) has no provider `.enc` files. This session only uses that store at run time, so the live e2e was not started. Seed worker agents stay on `loop`. Env fallback keys were not copied into Settings and were not passed to OpenHands.
- **Part 2:** OpenHands runs now get a studio MCP server (`search_data` and `load_skill`) plus the agent's own MCP servers. Each run gets a short-lived `atk_…` token (env only, hashed at rest, revoked when the run ends). Loop workers and supervisors still call the tools directly. The supervisor graph is unchanged.

## Real test results
- `RUN_REAL_LLM_TESTS=1` was not executed (no Settings key).
- Passes needed to switch seeds: 2 of 3. Actual: **0 of 3** (not started). Seeds remain `loop`.

## Cost comparison
- Not measured live. OpenHands would report `llm.metrics.accumulated_cost` from the **isolated** SDK (its own `litellm>=1.93.0`). The API records that number on the run / agent / role. Our gateway's `completion_cost` still uses **litellm 1.83.0**, so a same-token total can drift if model price tables changed between those versions. Re-run this check after a Settings key exists.

## LiteLLM pin (not upgraded)
- Keep **`litellm==1.83.0`**.
- Moving to **1.93.0** does **not** look safe: published 2026-07-19, but GHSA-3cv6-jpf6-8222 (authenticated SSRF / credential exfiltration) affects `<1.94.0` and is patched in `1.93.2` / `1.96.2` (and other backports). 1.93.0 also throttles over-budget keys instead of rejecting them, and moves OpenTelemetry error attributes under `litellm.*`.
- If we ever move, jump to a patched release at least two weeks old (not 1.93.0 itself), and re-run gateway tests. Out of scope here.

## MCP wrapper
- `POST /mcp` JSON-RPC and host-side `python -m runtime.mcp.stdio`.
- Token in MCP child `env`, never argv, logs, or API responses (`atk_` is redacted).
- Agent-scoped sources and skills. Calls logged as `MCP_TOOL_CALLED` with name + result size only.

## Test plan
- [x] Mocked MCP pytest: same results as direct tools; own sources/skills only; missing/wrong/expired tokens refused; token dead after the run; events have no secrets; OpenHands spec includes studio MCP + agent MCP.
- [x] Role-name AST scan covers `api/runtime/mcp/*.py`; graph import scan still passing.
- [x] Full API pytest: 142 passed, 7 skipped. Known tic-tac-toe PNG flake failed once (not worse).
- [x] Vitest 80 passed; typecheck passed.
- [ ] Real OpenHands + Docker e2e: blocked on Settings key.

## Out of scope / follow-ups
- Save a provider key in Settings, then run `RUN_REAL_LLM_TESTS=1` three times and switch seeds if 2/3 pass.
- Live cost comparison vs gateway 1.83.0.
- Notes/memory, QA, badges, fallbacks, automation defaults, supervisor graph, main litellm pin.
