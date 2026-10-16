## Summary

- Add a **Backend Engineer** library role and a **Node Express + Prisma + SQLite** stack (allow-list, `express-prisma` scaffold with `/health` + test, three evals).
- A project can have **several members**. Add agent is on the chat info panel; overlapping zones (except read-only `package.json` / `tsconfig*`) return 409 and show in red. Writes to those shared files wait until the other member is idle.
- **route_task** assigns by `@mention`, then scope, then stack keywords, then a classifier; “both” splits into two child tasks **backend first**. Backend `complete` writes `api/CONTRACT.md` and the frontend run reads it.
- Thread messages show **agent name and colour**. One active run per project is unchanged; child tasks queue.

**Note:** `origin` was missing at push time and was re-added as `https://github.com/amirshahzadhashmi7145/Atelier-V2.git`.

## What is real vs not

| Real now | Not yet |
|----------|---------|
| Backend Engineer library template, Node stack, evals | Reviewer / team lead, PM, QA |
| Multi-member projects, overlap block, @mention | Live MCP/API tool dispatch |
| Scope/keyword/classifier routing and backend-first split | Anthropic adapter |
| `api/CONTRACT.md` handed to the frontend run | |

## Test plan

- [x] Connect 4 precondition on main: `RUN_REAL_LLM_TESTS=1 pytest tests/test_gemini_provider.py::test_real_connect_four_gemini` — passed in 5m31s
- [x] `GATEWAY_MOCK=1 pytest tests/test_s12_backend.py` — import, overlap, route_task (scope/keyword/classifier/split), CONTRACT.md, @mention, shared-file idle (10 passed, 1 skipped)
- [ ] Playwright: add member, red overlap, two coloured replies (`chat.spec.ts`)
- [ ] `RUN_REAL_LLM_TESTS=1` todo app with Node API + React UI (gated)

## New dependencies

none

## Session summary (S12)

Session: S12 feat/backend-engineer  
Built: A Backend Engineer can share a project with the Frontend Engineer. Routing sends work to the right member or splits it backend-first with an API contract file.  
Decisions: `@Backend`/`@Frontend` is the first token only; `package.json` and `tsconfig*` may overlap as read-only; shared writes are refused while the other member is working.  
Failures / known gaps: Real todo-app LLM run is gated; reviewer/PM/QA roles are out of scope. Pre-existing web typecheck errors on main are unchanged.  
New dependencies: none  
Follow-ups: Team Lead / reviewer; run the live todo-app test with `RUN_REAL_LLM_TESTS=1`.
