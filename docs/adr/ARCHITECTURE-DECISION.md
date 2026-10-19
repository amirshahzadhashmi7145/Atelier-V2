# Architecture decision: commodity layers and our own logic

Roles stay data. The human stays out of the loop unless automatic checks fail.

## Picture

```
User request (one prompt)
        |
        v
  Worker agents          ← do the work (OpenHands later)
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

### 2. OpenHands for every worker (later)

**Chose:** OpenHands as the engine for worker agents, whatever their role.

**Why:** Coding, tools, and workspace loops are a commodity. We should not keep a second worker runtime per role.

**Rejected:** A custom worker loop per role, or OpenHands only for Frontend.

**Trade-off:** We will wrap our data sources and skills as MCP so OpenHands can use them. Until that session, the existing worker loop stays.

### 3. LangGraph for every supervisor (this session)

**Chose:** LangGraph for supervisor agents. Keep `record_review`, max two reworks, and the review spend cap. Stack reviewer, then QA, then PM on the same generic logic.

**Why:** Supervisors are a graph of review and handoff, not a coding agent. One graph, parameterized by role data.

**Rejected:** A new review implementation per supervisor role. Putting supervisors on OpenHands.

**Trade-off:** Two engines (OpenHands workers, LangGraph supervisors) instead of one. The split matches the worker vs supervisor tag.

**Pins:** `langgraph==1.2.12` (published 2026-09-21 — newest 1.2.x at least two weeks old as of 2026-10-19; 1.2.13–1.2.16 are newer than that floor). `langgraph-checkpoint-sqlite==3.1.1` (published 2026-07-30) matches our SQLAlchemy SQLite app database; 3.1.2 (2026-10-12) is too new. The checkpointer writes LangGraph tables into the same SQLite file as `documents`.

**Graph:** One generic graph for every supervisor role: `plan` → `dispatch` → `wait` → `review` → `advance` → `wrap-up`. What a supervisor does is role data and prompt, never a Python branch on a role name. A role added in Settings runs on this same graph.

**State:** The graph state is the supervisor's memory: plan id, task ids, status per task (`planning` / `working` / `reviewing` / `escalated` / `done`), decision ids, handoff ids, and current layer. It stores board ids, not copies of tasks, handoffs, or feedback. The SQLite checkpointer saves after every node so a run continues after an API restart.

**WorkerRunner:** Workers are behind a one-method interface (`run(task_input) → ids when the handoff note is written`). `LoopWorkerRunner` is today's loop. Session 17 adds OpenHands behind the same interface. Graph nodes must not import how a worker runs.

**Model calls:** Every model call inside a graph node goes through `gateway/llm.py` (via the existing run loop). No LangChain chat wrappers and no direct provider clients in graph code.

### 4. One MCP server for our tools (later)

**Chose:** Wrap `search_data` and `load_skill` as a small MCP server. Pass agent-configured MCPs straight through.

**Why:** OpenHands already speaks MCP. We should not invent a second tool bus.

**Rejected:** Reimplementing data/skill tools inside OpenHands, or a large MCP surface.

**Trade-off:** A thin adapter to maintain. Agent MCPs stay the user's responsibility.

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

## What this session does not change

OpenHands, the MCP wrapper, the project notes file and long-term memory, a QA role, suggestion badges, fallback models, and automation defaults. Those are later sessions. Models come only from provider API keys (OpenAI and Gemini now; others later). Nothing about roles, providers, or models is hardcoded as the product surface: the UI writes data, the gateway takes a model name.
