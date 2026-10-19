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

**Trade-off:** The Python SDK does not fit this repo's LiteLLM pin (`openhands-sdk==1.51.0` wants `litellm>=1.93.0`; we stay on `litellm==1.83.0` after the March 2026 supply-chain incident). Runs therefore use the SDK in an isolated `uv` process plus a Docker sandbox. Seed agents stay on the loop engine until a real Docker test with a Settings-stored key passes.

**Pins:** `openhands-sdk`, `openhands-tools`, `openhands-workspace`, and `openhands-agent-server` all **1.51.0** (published 2026-10-03 — 16 days old as of 2026-10-19; 1.54.0+ are newer than the two-week floor). Docker image `ghcr.io/openhands/agent-server:1.51.0-python`. The four packages live in `api/runtime/openhands/requirements.txt`, not `api/pyproject.toml`.

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

### 5. Memory (later)

**Chose:** LangGraph state for supervisors. A project notes file in the repo for workers.

**Why:** Supervisors need in-run graph state. Workers need something the next worker (and the user) can read in the repo.

**Rejected:** A shared vector store as the first memory. Role-specific memory services.

**Trade-off:** Notes files can go stale; graph state dies with the run. Good enough until we have evidence we need more.

### 6. Model suggestions from run stats (later)

**Chose:** Suggest a model per role from first-try approval rate, rework count, and cost per task. Show a "Suggested" badge. Under 5 runs, show "not enough data yet". Storage for role-fit labels is keyed by role id (data), not a fixed role list.

**Why:** Fit should come from this studio's runs, not a hardcoded ranking.

**Rejected:** Shipping a canned "best model for Frontend" list. Building the suggestion engine in this session.

**Trade-off:** Early users see no badge. That is honest.

### 7. Automation: escalation only (later)

**Chose:** Plan approval and "user decides after two reworks" become escalation-only. Agents resolve among themselves first.

**Why:** Principle B. The user asked for a team, not a click-through wizard.

**Rejected:** Keeping mandatory plan approval as the long-term default.

**Trade-off:** More autonomy means a sharper need for spend caps and rework limits — those stay automatic.

## Role model and the task board (this session)

**Chose:** Every role is a document: id, name, kind (`worker` or `supervisor`), `reportsTo`, layer order, zones, tags, colour, and an optional contract file the role writes for others to read. Seeded roles (Frontend Engineer, Backend Engineer, Team Lead) are rows, not branches in code. Adding a role is a UI/API write.

The task board is the only channel between agents. Three record types live in the app database:

- **Task** — id, parent, assigned agent, acceptance criteria, status, rework count
- **Handoff note** — written when a worker calls `complete` (summary, files, evidence per criterion, open questions)
- **Review feedback** — written when a supervisor calls `record_review` (verdict plus itemised wrong/expected)

A rework run is fed the task, the last handoff note, and the latest feedback. After two reworks the task moves to the next supervisor layer (`reportsTo` / layer order). If none remains, it reaches the user. An approval walks the same chain upward until the top, then the task is done.

**Why:** Principle A (roles are data) and principle B (agents talk to each other; a person is last). QA later is another supervisor row on this chain.

**Rejected:** Routing or review that matches role names. A second message bus besides the board. Building a QA role in this session.

## OpenHands worker runner (this session)

**Chose:** `OpenHandsWorkerRunner` implements `WorkerRunner`. Each task run copies the project repo onto the task branch, starts a Docker sandbox (`DockerWorkspace` with `mount_dir`), and gives OpenHands the compiled prompt plus the board packet (task, acceptance criteria, last handoff, latest feedback). After the process exits we always tear the sandbox down.

**Checks around it:** Files changed come from `git diff`, not from the model. A path outside the role zones, a new package off the stack allow-list, or a failing `build_test` (run by us) rejects the run. A rejection is a rework: automatic feedback, `reworkCount` incremented, and the worker retries with that note. OpenHands questions or "blocked" become handoff open questions for the supervisor, not a user prompt.

**Keys:** The decrypted provider key is passed only as `LLM_API_KEY` on the isolated process. It is never written to disk, sandbox files, logs, or API responses. Event logs are redacted with `gateway.keys.redact` before save.

**Costs:** OpenHands reports cost per call (`llm.metrics.accumulated_cost`). We add it to the run, `agent-spend`, and `role-spend` the same way the gateway does. Hitting `maxSpendPerRunUsd` stops the run.

**Engine per agent:** `workerEngine` is data (`loop` | `openhands`), default `loop`. Seed agents stay on `loop` until a real Docker test with a Settings-stored key passes 2 of 3 times.

## MCP wrapper and run tokens (this session)

**Chose:** One JSON-RPC MCP server (`POST /mcp` and a host-side stdio process) exposing `search_data` and `load_skill` through the same Python as the loop tools. Each OpenHands run gets an `atk_…` token at start; the token is hashed in the database, passed only in the MCP child environment (never argv, disk, or logs), and revoked when the run ends. Requests without a valid token are refused. An agent only searches its own data sources and only loads skills on its `skillIds`. Each call is recorded on the run as `MCP_TOOL_CALLED` with the tool name and result size, not the result body.

**Why:** OpenHands needs our tools, but it must not see decrypted provider keys or another agent's skills and sources.

**Rejected:** A shared long-lived MCP API key. Putting `search_data` / `load_skill` in the Docker sandbox as local functions.

**Trade-off:** The stdio server runs in the API process environment so it can read the same SQLite database. The Docker sandbox still cannot reach our DB except through MCP.

**Git origin:** S15–S17 repeatedly found `origin` missing at push time. Nothing in this repo runs `git remote remove`. `.git/config` was empty (no remotes, no `core` section). Project `git init` only runs under `PROJECTS_DIR`, and tests point that at a temp dir. The writer is outside the repo: Cursor's `git_write` sandbox can persist a stripped `.git/config` after an agent commit. `scripts/ensure_origin.sh` plus a pytest autouse restore `https://github.com/amirshahzadhashmi7145/Atelier-V2.git` when the remote is missing.

## What this session does not change

The project notes file and long-term memory, a QA role, suggestion badges, fallback models, automation defaults, the supervisor graph, and the main `litellm==1.83.0` pin. Models come only from provider API keys (OpenAI and Gemini now; others later). Nothing about roles, providers, or models is hardcoded as the product surface: the UI writes data, the gateway takes a model name.
