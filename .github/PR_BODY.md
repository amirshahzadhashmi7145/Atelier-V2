## What

The chat shows the agent's work as it happens, and evals are real runs instead of an automatic pass.

What is real: the gateway streams text. Each piece is a MODEL_DELTA on the existing SSE channel, then one MODEL_OUTPUT per model call. The thread grows the reply, shows tool lines, and replaces that with the summary, the files, and the links. A failed run (spend cap, loop, a refused tool) is an agent message with Try again. "Run evals" creates one run per eval in a throwaway folder, judges `build_and_tests` and `build_tests_and_screenshots`, stores pass or fail with cost, duration, and a link, and blocks Set active until every eval on that version passed. Those runs count against the spend cap. Settings > Models can compare models. Compiled prompt counts use tiktoken. Messages older than the last 20 are summarised onto the project and included in the next run. In Docker, the container can reach the npm registry, GitHub, and the preview host; a connection to another host is refused.

What is not real yet: the GitHub branch, push, and pull request path. The test is in the suite and did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. An empty screenshot file can satisfy the viewport check when Playwright cannot launch. The mock preview in the web unit tests still estimates tokens as characters divided by four. Studio browser tests still use the mock, which marks evals as pass without a run. Backend Engineer, routing rules, and supervisors are not in this PR. route_task still assigns the only member.

## Why

The engine could finish a task, but the thread only updated when the run ended, and every eval passed. This session makes the same channel show the work, and makes Set active mean the evals actually passed.

## How I tested

- `uv run --directory api pytest` — 17 passed, 2 skipped (the real OpenAI landing-page test, and the GitHub test because the token is empty). The Docker allow-list test ran here and a CONNECT to example.com returned 403.
- `pnpm typecheck` — pass
- `pnpm lint` — pass (the existing react-virtual and img warnings)
- `pnpm test` — 77 passed
- `pnpm test:e2e` — 12 passed on the mock studio, then 3 passed against the API with the model mocked at the gateway: streaming text appears before the summary, Run evals shows a pass chip and enables Set active, and a spend-cap failure shows Try again.

## Screenshots

/chat shows the reply growing under the user message, with a cursor while the run is active and a short line for the tool in progress. When the run finishes, that is replaced by the summary, then the files, then the preview or pull request link. A failed run shows the reason and Try again. The agent editor shows pass or fail, cost, duration, and a link to the run. Settings > Models has Run evals and a comparison table.

## New dependencies

- tiktoken: count compiled prompt tokens with OpenAI's tokenizer. Actual usage still comes from the API response.

## Out of scope / follow-ups

A Backend Engineer agent, routing rules, and supervisors. Those replace route_task later. They are not in this PR. The GitHub test needs a token in api/.env and RUN_GITHUB_TESTS=1.

## S7 feat/streaming-real-evals

Session: S7 feat/streaming-real-evals
Built: The chat shows the agent's text as it arrives, then replaces it with the summary, the files, and the links. Evals are real runs. A version can be set active only when every eval on it passed. Settings > Models can run one agent's evals across models. Compiled prompts are counted with tiktoken. Older chat is summarised onto the project. The Docker sandbox refuses hosts outside the allow-list.
Decisions: S6 was still unmerged, so this branch starts from feat/real-engine-chat. MODEL_DELTA rows are folded into one MODEL_OUTPUT when the model call finishes, and sequence numbers are packed so the event log stays contiguous. The chat batches those pieces about every 50ms. Eval runs use the same loop in a folder that is deleted afterwards. Pass is the string `pass`. Mocked studio tests still mark evals as pass without a run. The "best in your runs" badge still needs five completed runs; compare runs count toward that. DEV LOCAL MODE is unchanged when Docker does not answer.
Failures / known gaps: The GitHub branch, push, and pull request test is in the suite and did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. A screenshot pass can be met by an empty image when Playwright cannot launch; the viewport is recorded and console errors are empty. The mock preview in the web unit tests still estimates tokens as characters divided by four. Saved versions use tiktoken. Backend Engineer, routing rules, and supervisors are not in this session. route_task still assigns the only member.
New dependencies: tiktoken, so compiled prompt counts use OpenAI's tokenizer. Actual usage still comes from the API response.
Follow-ups for the next session: Put a GitHub token in api/.env and run the throwaway-repo test with RUN_GITHUB_TESTS=1. A Backend Engineer agent. Routing rules that replace route_task.
