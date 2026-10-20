# Architecture decision: commodity layers and our own logic

Roles stay data. The human stays out of the loop unless automatic checks fail.

## Picture

```
User request (one prompt)
        |
        v
  Worker agents          ← OpenHands (or the loop engine) behind WorkerRunner
        |
        v
  Supervisor: reviewer   ← record_review, max two reworks, spend cap
        |
        v
  Supervisor: QA         ← same generic supervisor loop
        |
        v
  Supervisor: PM         ← same generic supervisor loop
        |
        v
  LiteLLM gateway        ← every model call, every role
```

Worker and supervisor agents share one shape: a role, a "reports to", and a worker or supervisor tag. New roles are rows in the UI, not new code paths. Supervisors stack; they do not fork the architecture.

## Principles

### A. Generic roles, fixed shape

**Chose:** Roles are data. Workers do work. Supervisors review. More supervisor layers (QA, then PM) sit on the same loop.

**Why:** Frontend, Backend, and Team Lead already fit this shape. QA and PM will too. Hardcoding a role in routing or review logic means every new role is an architecture change.

**Rejected:** A separate engine, graph, or review protocol per role.

**Trade-off:** Role-specific skill lives in prompts, tools, zones, and evals — not in Python. Routing, review, and colour must read role documents; they must not name a role.

### B. Minimal human input

**Chose:** One user request. Agents plan, split, build, review, test, and pass work to each other. A human is pulled in only for a spend cap, used-up rework limit, an escalation, or a task no agent can clarify.

**Why:** Safety belongs in automatic checks (zones, package allow-list, spend caps, build and tests), not in clicking through every step.

**Rejected:** Plan approval and "user decides after two reworks" as the default path. Those become escalation-only in a later session.

**Trade-off:** Bad work can travel further before a person sees it. Caps, zones, and stacked supervisors are the brake.

## The seven layers

### 1. LiteLLM as the single model layer (this session)

**Chose:** Open-source LiteLLM, pinned to **1.83.0**. Every live model call goes through `gateway/llm.py`. The gateway takes a model, messages, tools, and a run id. It does not know roles.

**Why:** One adapter for OpenAI, Gemini, and providers added later. Cost and tool-calling capability come from LiteLLM instead of our own price tables and SDK branches.

**Rejected:** Calling the OpenAI SDK and Google GenAI from separate provider files. Local / Ollama models as a product path.

**Trade-off:** We depend on LiteLLM's mapping quality (especially Gemini thought signatures). Mock tests still use scripted turns; live calls use LiteLLM.

**Pin / security:** In March 2026, PyPI copies of `litellm` **1.82.7** and **1.82.8** were compromised (supply-chain). Those versions must never be installed. **1.83.0** is the first release after LiteLLM's CI/CD v2 rebuild and is the version we pin. Do not loosen the pin to a range that could pull 1.82.7 or 1.82.8.

### 2. OpenHands for every worker (this session)

**Chose:** OpenHands as the engine for worker agents, whatever their role. Supervisors still call workers only through `WorkerRunner`. The supervisor graph is unchanged.

**Why:** Coding, tools, and workspace loops are a commodity. We should not keep a second worker runtime per role.

**Rejected:** A custom worker loop per role, or OpenHands only for one seed role. Importing `openhands-sdk` into the API process.

**Trade-off:** The Python SDK does not fit this repo's LiteLLM pin (`openhands-sdk==1.51.0` wants `litellm>=1.93.0`; we stay on `litellm==1.83.0` after the March 2026 supply-chain incident). Runs therefore use the SDK in an isolated `uv` process plus a Docker sandbox. Seed agents stay on the loop engine until a real Docker test with a Settings-stored key passes 2 of 3 times.

**Pins:** `openhands-sdk`, `openhands-tools`, `openhands-workspace`, and `openhands-agent-server` all **1.51.0** (published 2026-10-03 — 17 days old as of 2026-10-20; 1.54.0+ are newer than the two-week floor). Docker image `ghcr.io/openhands/agent-server:1.51.0-python`. The four packages live in `api/runtime/openhands/requirements.txt`, not `api/pyproject.toml`.

**Isolated litellm:** The sidecar is pinned to **litellm==1.96.2** (published 2026-08-11). [GHSA-3cv6-jpf6-8222](https://github.com/BerriAI/litellm/security/advisories/GHSA-3cv6-jpf6-8222) is authenticated SSRF / credential exfiltration. Affected: main line below 1.94.0, plus 1.93.0–1.93.1, 1.94.0–1.94.2, 1.95.0, and 1.96.0–1.96.1. Patched: 1.93.2 (1.93 backport), 1.94.3, 1.95.1, 1.96.2. `openhands-sdk==1.51.0` accepts `litellm>=1.93.0`; 1.93.0 itself is not safe, so we do not use the SDK's lower bound. 1.96.2 is the mainline patched release and is older than the two-week floor (2026-10-06). Transitive pins are locked in `requirements.lock`. A startup check refuses to start an OpenHands run if the isolated environment's `litellm` is not exactly 1.96.2. The API process stays on `litellm==1.83.0`.

### 3. LangGraph for every supervisor (this session)

**Chose:** LangGraph for supervisor agents. Keep `record_review`, max two reworks, and the review spend cap. Stack reviewer, then QA, then PM on the same generic logic.

**Why:** Supervisors are a graph of review and handoff, not a coding agent. One graph, parameterized by role data.

**Rejected:** A new review implementation per supervisor role. Putting supervisors on OpenHands.

**Trade-off:** Two engines (OpenHands workers, LangGraph supervisors) instead of one. The split matches the worker vs supervisor tag.

**Pins:** `langgraph==1.2.12` (published 2026-09-21 — newest 1.2.x at least two weeks old as of 2026-10-19; 1.2.13–1.2.16 are newer than that floor). `langgraph-checkpoint-sqlite==3.1.1` (published 2026-07-30) matches our SQLAlchemy SQLite app database; 3.1.2 (2026-10-12) is too new. The checkpointer writes LangGraph tables into the same SQLite file as `documents`.

**Graph:** One generic graph for every supervisor role: `plan` → `dispatch` → `wait` → `review` → `advance` → `wrap-up`. What a supervisor does is role data and prompt, never a Python branch on a role name. A role added in Settings runs on this same graph.

**State:** The graph state is the supervisor's memory: plan id, task ids, status per task (`planning` / `working` / `reviewing` / `escalated` / `done`), decision ids, handoff ids, and current layer. It stores board ids, not copies of tasks, handoffs, or feedback. The SQLite checkpointer saves after every node so a run continues after an API restart.

**WorkerRunner:** Workers are behind a one-method interface (`run(task_input) → ids when the handoff note is written`). `LoopWorkerRunner` still runs the in-process loop. An agent with `workerEngine: openhands` is handed to `OpenHandsWorkerRunner`. Graph nodes must not import how a worker runs.

**Model calls:** Every model call inside a graph node goes through `gateway/llm.py` (via the existing run loop). No LangChain chat wrappers and no direct provider clients in graph code.

### 4. One MCP server for our tools (this session)

**Chose:** Wrap `search_data` and `load_skill` as a small MCP server inside the API. Pass that server to every OpenHands run alongside the agent's own MCP servers. Loop workers and supervisors keep calling the tools directly.

**Why:** OpenHands already speaks MCP. We should not invent a second tool bus.

**Rejected:** Reimplementing data/skill tools inside OpenHands, or a large MCP surface.

**Trade-off:** The OpenHands sandbox never holds a provider key for our tools. It holds a short-lived run token instead.

### 5. Memory (this session)

**Chose:** Supervisors use LangGraph state. Workers use OpenHands session history plus one project notes file. Long-term cross-project memory comes later.

**Notes file:** Each project repo has one file at a path set in project settings (default `.atelier/NOTES.md`, size cap default 8192 bytes). It holds short, stable facts: stack, folder layout, conventions, API locations, decisions. Every worker run (loop or OpenHands) receives the current file as task input. OpenHands also gets it as an always-loaded skill, the same role `AGENTS.md` plays in current OpenHands docs. Workers cannot edit it: the path is on a protected list the zone check rejects even when the path sits inside the role zones. After a supervisor approves a task, the existing `advance` step proposes notes updates from the handoff (new stable facts only; task progress is dropped), applies them, commits on the task branch, and records the update on the task board. Near the size cap it rewrites the file shorter instead of appending.

**Why:** Supervisors already have in-run graph state. Workers need something the next worker (and the user) can read in the repo without a vector store.

**Rejected:** A shared vector store as the first memory. Role-specific memory services. Letting workers edit the notes file.

**Trade-off:** Notes files can go stale; graph state dies with the run; OpenHands session history does not survive a new conversation. Good enough until we have evidence we need long-term memory.

### 6. Model suggestions from run stats (this session)

**Chose:** Suggest a model per role from real runs only: first-try approval rate, average rework count, average cost per task, and task count. The dropdown marks the best model with a "Suggested" badge and a short reason. Best means highest first-try approval rate; if two are within 10 points, the cheaper wins. Below 5 tasks, show "not enough data yet". New agents default to the suggestion when one exists. Existing agents never switch on their own.

**Why:** Fit should come from this studio's runs, not a hardcoded ranking.

**Rejected:** Shipping a canned "best model for Frontend" list. Auto-switching models on agents the user already configured.

**Trade-off:** Early users see no badge. That is honest.

### 7. Automation: escalation only (this session)

**Chose:** "Approve plans before running" defaults to off. A person is asked only when a task escalates past the top supervisor, a spend cap is hit, or no agent can resolve an open question. Those three cases share one "Needs you" list. An answer is written to the task board and the waiting run continues.

**Why:** Principle B. The user asked for a team, not a click-through wizard.

**Rejected:** Keeping mandatory plan approval as the default path.

**Trade-off:** More autonomy means a sharper need for spend caps and rework limits — those stay automatic.

### 8. Backup models (this session)

**Chose:** Each agent may name a backup model. On provider error, timeout, or rate-limit the call retries once, then LiteLLM switches to the backup. A normal bad answer never switches. The run records which model actually ran and counts backup use separately. OpenHands gets the backup the same way (`LLM_BACKUP_MODEL` / `LLM_BACKUP_API_KEY` on the isolated process).

**Why:** Provider blips should not stop a run. A weak completion is a review problem, not a failover.

**Rejected:** Switching models because the answer looked wrong.

### 9. Lessons per role (this session)

**Chose:** A lessons table (role id, short text, source task id, created date). After rework then approval, the supervisor may write at most one short lesson for that worker's role when the feedback shows a mistake likely to repeat. No task details or project facts (those stay in the notes file). Every worker run receives its role's lessons in the task input. OpenHands also gets `get_lessons` on the studio MCP server. Cap per role (setting, default 20); when full, similar lessons merge. Settings > Roles shows lessons with delete.

**Why:** Repeatable process mistakes belong with the role, not the project.

**Rejected:** Embedding project facts in lessons. A vector store.

## Role model and the task board (this session)

**Chose:** Every role is a document: id, name, kind (`worker` or `supervisor`), `reportsTo`, layer order, zones, tags, colour, and an optional contract file the role writes for others to read. Seeded roles (Frontend Engineer, Backend Engineer, Team Lead, QA Engineer) are rows, not branches in code. Adding a role is a UI/API write. QA sits one layer above Team Lead (`reportsTo` / layer from data) and runs on the same supervisor graph. It reviews work the Team Lead approved, may run `build_test` and `headless_browser`, cannot write files, and sends bugs back through the normal rework loop.

The task board is the only channel between agents. Three record types live in the app database:

- **Task** — id, parent, assigned agent, acceptance criteria, status, rework count
- **Handoff note** — written when a worker calls `complete` (summary, files, evidence per criterion, open questions)
- **Review feedback** — written when a supervisor calls `record_review` (verdict plus itemised wrong/expected)

A rework run is fed the task, the last handoff note, and the latest feedback. After two reworks the task moves to the next supervisor layer (`reportsTo` / layer order). If none remains, it reaches the user. An approval walks the same chain upward until the top, then the task is done.

**Why:** Principle A (roles are data) and principle B (agents talk to each other; a person is last). QA is another supervisor row on this chain.

**Rejected:** Routing or review that matches role names. A second message bus besides the board. A separate QA graph.

## OpenHands worker runner (this session)

**Chose:** `OpenHandsWorkerRunner` implements `WorkerRunner`. Each task run copies the project repo onto the task branch, starts a Docker sandbox (`DockerWorkspace` with `mount_dir`), and gives OpenHands the compiled prompt plus the board packet (task, acceptance criteria, last handoff, latest feedback). After the process exits we always tear the sandbox down.

**Checks around it:** Files changed come from `git diff`, not from the model. A path outside the role zones, a new package off the stack allow-list, or a failing `build_test` (run by us) rejects the run. A rejection is a rework: automatic feedback, `reworkCount` incremented, and the worker retries with that note. OpenHands questions or "blocked" become handoff open questions for the supervisor, not a user prompt.

**Keys:** The decrypted provider key is passed only as `LLM_API_KEY` on the isolated process. It is never written to disk, sandbox files, logs, or API responses. Event logs are redacted with `gateway.keys.redact` before save.

**Costs:** The cost reported by the isolated OpenHands process (`llm.metrics.accumulated_cost`) is the source of truth for that run. Run details label it as such. We add it to the run, `agent-spend`, and `role-spend` the same way the gateway does. Hitting `maxSpendPerRunUsd` stops the run. Gateway-estimated prices are not mixed in, because the sidecar's LiteLLM pin and the API pin are different.

**Engine per agent:** `workerEngine` is data (`loop` | `openhands`), default `loop`. Seed agents stay on `loop` until a real Docker test with a Settings-stored key passes 2 of 3 times.

## MCP wrapper and run tokens (this session)

**Chose:** One JSON-RPC MCP server (`POST /mcp` and a host-side stdio process) exposing `search_data`, `load_skill`, and `get_lessons` through the same Python as the loop tools. Each OpenHands run gets an `atk_…` token at start; the token is hashed in the database, passed only in the MCP child environment (never argv, disk, or logs), and revoked when the run ends. Requests without a valid token are refused. An agent only searches its own data sources and only loads skills on its `skillIds`. Each call is recorded on the run as `MCP_TOOL_CALLED` with the tool name and result size, not the result body.

**Why:** OpenHands needs our tools, but it must not see decrypted provider keys or another agent's skills and sources.

**Rejected:** A shared long-lived MCP API key. Putting `search_data` / `load_skill` in the Docker sandbox as local functions.

**Trade-off:** The stdio server runs in the API process environment so it can read the same SQLite database. The Docker sandbox still cannot reach our DB except through MCP.

**Git origin:** S15–S17 repeatedly found `origin` missing at push time. Nothing in this repo runs `git remote remove`. `.git/config` was empty (no remotes, no `core` section). Project `git init` only runs under `PROJECTS_DIR`, and tests point that at a temp dir. The writer is outside the repo: Cursor's `git_write` sandbox can persist a stripped `.git/config` after an agent commit. `scripts/ensure_origin.sh` plus a pytest autouse restore `https://github.com/amirshahzadhashmi7145/Atelier-V2.git` when the remote is missing.

## What this session does not change

A PM role, upgrading the API's `litellm==1.83.0` pin, and any change to supervisor graph structure. New behaviour comes from role data, settings, and small additions to existing nodes. Models come only from provider API keys stored in Settings (OpenAI and Gemini now; others later). Nothing about roles, providers, or models is hardcoded as the product surface: the UI writes data, the gateway takes a model name.
