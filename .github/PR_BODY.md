## What

Chat no longer starts a run for every message. A greeting gets a direct reply, work outside the role gets one short refusal, and in-role work starts a run. Streaming keeps one bubble per model call. Teach adds a skill, a stack, and optional docs in one save.

What is real: MODEL_DELTA carries modelCallId and index and is pushed from memory. The database stores one MODEL_OUTPUT per call, in index order. The SSE response sends Cache-Control: no-cache, X-Accel-Buffering: no, and Connection: keep-alive. There is no Next.js proxy in front of that route. The thread shows "thinking Ns" until the first word, and "running: <command>" with elapsed seconds while a shell call is in progress. Shell commands default to 120 seconds, cap at 10 minutes, run with CI=1, non-interactive flags, and a closed stdin. A timeout kills the process and the agent sees the error. A command that does not exit is refused and points at the preview tool. raise_clarification accepts at most 3 questions and at most 1 round; the next attempt records an assumption on the summary. The user's answer is a user message. The chat page fills the viewport. Only the thread scrolls. At 768 the preview is a tab. Teach creates the skill, the stack, and a docs source when a URL is given, attaches them, and the compiled preview updates. Draft rules fills the sheet from a repo URL; with the gateway mocked it does not clone. A screenshot passes only when Playwright launched and the PNG matches the viewport. Otherwise the eval fails with "screenshot unavailable". A pre-commit script and a CI step scan tracked files for key patterns. .env.example values for *_KEY and *_TOKEN must be 8 characters or shorter. Package install still uses its allow-list.

What is not real yet: the GitHub branch, push, and pull request path. The test is in the suite and did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. The classifier's live path is one completion; the tests use a word list because GATEWAY_MOCK=1. Draft-from-repo clones only on that live path. Studio browser tests still use the mock, which marks evals as pass without a run. Backend Engineer, routing rules, and supervisors are not in this PR. route_task still assigns the only member. Git config was not changed, so .githooks/pre-commit is not installed until someone points hooks at that directory. CI runs the scan regardless.

## Why

Streams were mixing text from different model calls and writing every piece to the database. Small talk started a run. Teaching a stack took several forms. A missing screenshot could still pass an eval.

## How I tested

- `uv run --directory api pytest` — 24 passed, 2 skipped (the real OpenAI landing-page test, and the GitHub test because the token is empty).
- `pnpm typecheck` — pass
- `pnpm lint` — pass (the existing react-virtual and img warnings)
- `pnpm test` — 80 passed
- `pnpm test:e2e` — 12 passed on the mock studio, then 8 passed against the API with the model mocked at the gateway: two bubbles stay in order, "hello" is a direct reply, a long command shows "running: sleep 8", Teach attaches a skill and the preview updates, and the chat document element matches the viewport at 1920, 1280, and 768.
- `python3 scripts/scan_secrets.py` — pass. Tracked files have no key pattern. api/.env and web/.env.local are gitignored and are not scanned.

## Screenshots

The chat thread scrolls inside a page that stays at the viewport height. A greeting shows the agent's reply and no Working button. While a shell command runs, the thread says "running:" plus the command and a second count. Teach is a sheet on the agent page; after save the compiled preview names the new skill.

## New dependencies

None. CI uses gitleaks/gitleaks-action. The scanner is scripts/scan_secrets.py and uses the standard library.

## Out of scope / follow-ups

A Backend Engineer agent, routing rules, and supervisors. Those replace route_task later. They are not in this PR. The GitHub test needs a token in api/.env and RUN_GITHUB_TESTS=1.

## S8 feat/run-fixes-teach-streaming

Session: S8 feat/run-fixes-teach-streaming
Built: A chat message is labelled before a run exists. Greetings get a short reply in the thread, work outside the role gets one refusal, and in-role work starts a run. Each model call is its own bubble. Deltas stay in memory and only the merged text is stored. The chat page is the viewport height, the thread is the only scroller, and Teach saves a skill, a stack, and an optional docs source onto the agent in one request.
Decisions: The live classifier is one completion; under GATEWAY_MOCK the label is a word list so the suite stays offline. Live delta sequence numbers sit at 1_000_000 and up so they cannot replace a stored event, and the resume cursor ignores them. Clarification rounds live in a side record because the Run document drops unknown fields. A command that does not exit is refused before it starts and points at the preview tool. A screenshot counts only when Playwright launched and the PNG size matches the viewport. The secret scan skips gitignored files so api/.env can hold a token; .env.example is tracked and is scanned. Git config was not changed, so the hook file at .githooks/pre-commit is not installed by this commit. CI runs it, and runs gitleaks.
Failures / known gaps: The GitHub branch, push, and pull request test did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. Chromium has no document.scrollHeight; the test checks documentElement.scrollHeight against the viewport. Draft rules from a repo clones only when the gateway is not mocked. The mock studio still marks evals as pass without a run. Backend Engineer, routing rules, and supervisors are not in this session. route_task still assigns the only member.
New dependencies: none. CI calls gitleaks/gitleaks-action. The tree scan is a Python script in the repo.
Follow-ups for the next session: Put a GitHub token in api/.env and run the throwaway-repo test with RUN_GITHUB_TESTS=1. Point git at .githooks if the local hook should run. A Backend Engineer agent. Routing rules that replace route_task.
