# Live testing

This is how to run the full live test for Agent Studio. Keys come only from Settings. Do not put a provider key in `api/.env`, the shell, or any other file.

## 1. Save a key

1. Start the API and the web app (see the README).
2. Open Settings > Providers.
3. Paste an OpenAI (or Gemini) key and save it. It is stored encrypted. The browser never sees it again.
4. Refresh models so the dropdowns have names.

If no key is in that encrypted store, live tests skip. They will not fall back to the environment for this path.

## 2. Turn live tests on

In the same terminal that runs pytest:

```bash
export RUN_REAL_LLM_TESTS=1
```

Leave `GATEWAY_MOCK` unset (or anything other than `1`).

Docker is required for OpenHands worker runs.

## 3. Commands

From the repo root:

```bash
uv run --directory api pytest
pnpm --dir web typecheck
pnpm --dir web test
```

To watch only the live OpenHands path:

```bash
RUN_REAL_LLM_TESTS=1 uv run --directory api pytest tests/test_s17_openhands.py -k live
```

The tic-tac-toe screenshot check should be stable. Run it a few times if you are verifying the flake fix:

```bash
for i in 1 2 3 4 5; do
  uv run --directory api pytest tests/test_engine.py -k tic_tac_toe_ui_reaches -q
done
```

## 4. What a pass looks like

- Mocked API tests pass (including QA on the same graph, suggestions, Needs you, backup models, and lessons).
- Vitest and typecheck pass.
- Live tests that need a Settings key run instead of skip.
- An OpenHands worker run finishes, writes a handoff, and shows cost labelled as coming from the OpenHands process.
- No test reads `OPENAI_API_KEY` or `GEMINI_API_KEY` from the environment for a live call.

## 5. Full-team scenario

In Chat, create a project whose members are:

- Frontend Engineer
- Backend Engineer
- Team Lead
- QA Engineer

Leave **Approve plans before running** off (the default). Type:

> build a todo app with login

Then leave it alone.

What should happen:

1. The Team Lead splits the work and assigns workers. You are not asked to approve the plan.
2. Workers run (loop or OpenHands, from each agent's settings).
3. The Team Lead reviews each child. Bugs go back to the original worker (at most two reworks).
4. Work the Team Lead approved goes to QA. QA checks the stated criteria against the preview, with evidence, and does not write files.
5. You only see **Needs you** if something escalates past QA, a spend cap is hit, or no agent can resolve an open question.

A pass is: the parent task completes, or it stops in Needs you with one clear question and a link to the task history. Anything in between that asks you to click through ordinary steps is a failure of this scenario.
