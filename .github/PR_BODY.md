## Summary
- Workers can run on OpenHands through the existing `WorkerRunner` interface. The supervisor graph is unchanged. `LoopWorkerRunner` still runs when `workerEngine` is `loop`.
- After each OpenHands run we take files from `git diff`, reject zone / allow-list / `build_test` failures as an automatic rework, record OpenHands cost on the run, agent, and role, and save a redacted event log linked from the task history page.
- **Origin remote:** S15–S17 found `origin` missing at push time. Nothing in this repo runs `git remote remove`. `.git/config` was empty (no remotes, no `core` section). Project `git init` only runs under `PROJECTS_DIR` (tests use a temp dir). The writer is outside the repo: Cursor's `git_write` sandbox can persist a stripped `.git/config` after an agent commit. `scripts/ensure_origin.sh` plus a pytest session fixture restore `https://github.com/amirshahzadhashmi7145/Atelier-V2.git`.

## Pins
- `openhands-sdk`, `openhands-tools`, `openhands-workspace`, `openhands-agent-server` **1.51.0** (published 2026-10-03, 16 days old as of 2026-10-19). 1.54.0+ are newer than the two-week floor.
- Docker image `ghcr.io/openhands/agent-server:1.51.0-python`.
- These packages are **not** in `api/pyproject.toml`: 1.51.0 requires `litellm>=1.93.0`, and this API stays on `litellm==1.83.0` after the March 2026 supply-chain incident. Live runs use `uv run --isolated --with-requirements api/runtime/openhands/requirements.txt`.

## Test plan
- [x] Mocked pytest (`tests/test_s17_openhands.py`): WorkerRunner, task packet, zone / package / build rejects, auto-rework feedback, files from diff, cost, spend cap, event log link, sandbox cleanup, keys redacted, engine switch, LoopWorkerRunner dispatch, MCP pass-through (no `search_data` / `load_skill`).
- [x] Role-name AST scan extended to `api/runtime/openhands/*.py`; graph import scan still passing.
- [x] Full API pytest: 135 passed, 7 skipped. Known tic-tac-toe PNG size flake failed once and is not worse.
- [x] Vitest 80 passed; `pnpm typecheck` passed; eslint 0 errors.
- [ ] Real OpenHands + Docker e2e (`RUN_REAL_LLM_TESTS=1`): **not run** in this session (skipped). Seed agents stay on `loop` until that test passes.

## Out of scope / follow-ups
- MCP wrapper for `search_data` and `load_skill` (session 18).
- Project notes / long-term memory, QA role, suggestion badges, fallback models, automation defaults.
- No supervisor graph changes.
- Switch seed worker agents to `openhands` after the real Docker test passes.
