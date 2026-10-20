## Summary
- **Stacked on #20** (`feat/s18-openhands-live-mcp`). Do not merge until #20 lands.
- Isolated OpenHands sidecar is locked to **litellm==1.96.2** (GHSA-3cv6-jpf6-8222). A startup check refuses a run if the isolated env is not that version. API stays on **litellm==1.83.0**.
- Each project has one notes file (default `.atelier/NOTES.md`). Workers receive it; they cannot edit it. After a supervisor approves a task, `advance` updates the file from the handoff (stable facts only), commits it on the task branch, and records it on the task board.

## Isolated litellm pin
- Advisory: [GHSA-3cv6-jpf6-8222](https://github.com/BerriAI/litellm/security/advisories/GHSA-3cv6-jpf6-8222) (authenticated SSRF / credential exfiltration).
- Unsafe: main line `<1.94.0`, plus 1.93.0–1.93.1, 1.94.0–1.94.2, 1.95.0, 1.96.0–1.96.1. `openhands-sdk==1.51.0` asks for `litellm>=1.93.0`; 1.93.0 is not safe.
- Pin: **1.96.2** (published 2026-08-11, older than the 2026-10-06 two-week floor). Transitive pins in `api/runtime/openhands/requirements.lock`.
- `ProcessOpenHandsClient` refuses to start if `import litellm; litellm.__version__` is not `1.96.2`.

## Live OpenHands run
- The Settings encrypted store (`~/.atelier-projects/.secrets/providers`) still has **no `.enc` files**. Part 2 stopped. The live key was not read from env, argv, logs, or files.
- `RUN_REAL_LLM_TESTS=1` skipped: `no provider key in the Settings encrypted store`.
- Passes needed to switch seeds: 2 of 3. Actual: **0 of 3** (not started). Seed worker agents stay on `loop`.

## Cost comparison
- Not measured live. OpenHands would report `accumulated_cost` from isolated litellm **1.96.2**. Gateway `completion_cost` still uses API litellm **1.83.0**. The gap is expected if price tables changed; pricing logic was not changed this session.

## Project notes
- Path and size cap live on the project (`PATCH /projects/{id}`). Defaults: `.atelier/NOTES.md`, 8192 bytes.
- Loop and OpenHands workers get the current file in task input. OpenHands also gets it as an always-loaded skill (same role as `AGENTS.md` in current OpenHands docs). We do not write `AGENTS.md` into the repo.
- Zone check rejects worker edits to the notes path even when it sits inside the role zones.
- On approve, `advance` extracts new stable facts from the handoff, drops task progress, rewrites shorter near the cap, commits on `task/{id}`, and adds a `notes` board event.

## Test plan
- [x] OpenHands run refused when isolated litellm is not 1.96.2.
- [x] Notes file in loop and OpenHands task input.
- [x] Worker edit of the notes file rejected (OpenHands zone check + loop `files` tool).
- [x] Supervisor approval adds a new fact and records it on the task board; task progress is not written.
- [x] Size limit triggers a shorter rewrite.
- [x] Role-name AST scan covers `api/runtime/notes.py` and existing OpenHands/MCP files; graph import scan still passing.
- [x] Full API pytest: 149 passed, 7 skipped. Known tic-tac-toe PNG size flake failed (not worse; screenshot dimensions only).
- [x] Vitest 80 passed; typecheck passed.
- [ ] Real OpenHands + Docker e2e ×3: blocked on Settings key.

## Out of scope / follow-ups
- Save a provider key in Settings, then run `RUN_REAL_LLM_TESTS=1` three times and switch seeds if 2/3 pass.
- Live cost comparison vs gateway 1.83.0.
- Long-term cross-project memory, QA role, suggestion badges, fallback models, automation defaults, API litellm pin, supervisor graph structure beyond the notes update in `advance`.
