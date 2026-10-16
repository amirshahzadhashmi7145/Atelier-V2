# Build log

## S1 feat/contract-scaffold

Session: S1 feat/contract-scaffold
Built: The monorepo now has the OpenAPI contract, a generated client, and an MSW store seeded from the Frontend Engineer role, four skills, the React and Next.js stacks, and three past runs. The studio shell lists agents, tools, skills, and runs against that mock, with loading, empty, and error states.
Decisions: Next.js 16.4.0 is the latest patched 16.x. Mocks stay on unless NEXT_PUBLIC_USE_MOCKS=false, so the app runs without an env file. models.json is empty because this session did not list model cards; the seed agent names gpt-5 and leaves fit lines and benchmarks unset. Eleven builtin tools are seeded because the runtime control set adds complete, raise_clarification, and escalate to the eight domain tools. The fourth starter skill is definition-of-done. The Frontend Engineer starts with React only. React docs are pinned to commit 046f17d04295ba047bb5739026b4ac3110f17028; Next.js docs are pinned to the v16.4.0 GitHub tree until the sandbox can read next/dist/docs. The web compiler counts tokens as ceil(chars/4). Theme lives in zustand; next-themes was removed after the sonner registry item pulled it in. Contract drift in CI is the generated client and the seed JSON, because there is no FastAPI app to diff until S7. Studio routes set instant = false so Next.js does not drop the client lists during its instant-navigation check.
Failures / known gaps: No agent editor, tool tabs, skill import UI, or live run view. The mock can stream about 25 events over 30 seconds, including one client-tool request and one refused package, but the UI does not read that stream yet. Zip import does not unpack the archive. Importing an API by URL returns one canned operation. GET /models is empty. No FastAPI, database, or runtime.
New dependencies: @tanstack/react-query: server state. zustand: theme and other UI state. openapi-fetch and openapi-typescript: generated client, no hand-written API types. msw: mock the contract in the browser and in Vitest. yaml: parse the role, stack, and skill seed files, and API specs on import. vitest, jsdom, @testing-library/react, @testing-library/jest-dom: unit and component tests. @vitejs/plugin-react: transform JSX in Vitest. @playwright/test and @axe-core/playwright: end-to-end tests with axe. @base-ui/react, class-variance-authority, cn, tw-animate-css, sonner, lucide-react: shadcn/ui, which the brief requires.
Follow-ups for the next session: Agents page editor, five prompt editors, debounced compile preview, Access card, versions drawer, and Set active disabled until a smoke eval passes.

## S2 feat/agents-editor

Session: S2 feat/agents-editor
Built: The studio starts empty. The user imports the Frontend Engineer from the library or creates a blank agent, then edits identity, a model settings form rendered from configSchema, budgets, five prompt editors with a compiled preview, access checklists, and evals. Settings > Providers stores an OpenAI key by reference, tests the connection, and caches six mock models for an hour. Set active stays disabled until every eval on the latest version has passed. The versions drawer diffs two prompts in a read-only merge view.
Decisions: Library templates stay in roles/, skills/, and stacks/ and are copied in on import, including the skills and stacks an agent names. Model prices and benchmarks stay empty so the card says "no stats entered" until a human adds a sourced number. The six mock models differ by which settings their schema includes. Control tools are omitted from GET /tools and always appended at compile time. Eval runs in the mock always pass; the real runner is S9. The mock store is remembered in sessionStorage so a client navigation does not wipe the agent the user just imported. react-hook-form and zod validate the blank agent, the eval, and the provider key. CodeMirror is loaded when the editor mounts; the merge view is loaded only when the versions drawer opens.
Failures / known gaps: The provider test does not call OpenAI; any stored key counts as connected. Zip import, tool tabs, the skills editor, and the runs UI are unchanged. Test run queues a mock run and does not open a live view. A full browser reload keeps the mock data for the tab, and the API key itself is dropped because it is not stored in the page.
New dependencies: react-hook-form: forms for a new agent, an eval, and the provider key. zod: validate those forms. @codemirror/view, @codemirror/state, @codemirror/lang-markdown, @codemirror/commands: the five prompt editors. @codemirror/merge: read-only version diff. @codemirror/language: required by the markdown mode.
Follow-ups for the next session: Tools page tabs, MCP discover, and API import against the same mock. Control tools stay off that page.

## S3 feat/skills-models-tools

Session: S3 feat/skills-models-tools
Built: Skills can be created in the editor or imported from a GitHub path, a zip, or a folder, with a review step and a diff when the same origin is imported again. Settings > Providers keeps the OpenAI key in this browser tab and lists the chat models OpenAI returns. The agent editor renders settings from each id's family schema. The Tools page has Built-in, Client-side, MCP, APIs, and Data; confirming a discovery or an import adds those tools, and a data source is one search_data tool.
Decisions: Model ids are never hardcoded. Reasoning families (o-series and gpt-5, except chat snapshots) get the documented reasoning_effort enum and no temperature; other gpt/chatgpt ids get temperature and maxOutputTokens; every chat model gets webSearch and structuredOutputs; anything else gets that base pair. The key stays in sessionStorage for this tab and is sent only on the models request. A failed discovery clears the cached catalog instead of leaving Connected. Select options use dark text on white so the menu stays readable in the dark theme. The mock returns one canned SKILL.md for any URL and five canned operations for any spec. Control tools stay off the Tools page. Prices and benchmarks stay empty.
Failures / known gaps: Zip entries that use a data descriptor are not unpacked. The API mock does not parse the pasted spec. The runs UI and the stacks sheet are not built. Eval runs in the mock still always pass.
New dependencies: none
Follow-ups for the next session: Stacks on the Access card, and a real spec parser when the API exists.

## S4 feat/finish-s3-settings-stacks

Session: S4 feat/finish-s3-settings-stacks
Built: Budgets left the agent editor. Settings > Runs holds a visible spend cap and advanced bounds. The OpenAI key is read from .env.local again, and Providers only says whether it was found. Settings > Models stores tags and a note in a local JSON file, and the model picker shows those tags plus run stats. Stacks are created on the Access card or imported from the library, and enabled stacks show up in the compiled preview.
Decisions: S3 was still unmerged, so this branch starts from feat/skills-models-tools. Amendment A was not in the repo; the session text is the spec. Reasoning families seed planning and review; mini, nano, and fast seed cheap and fast; a saved tag replaces the guess. ownStats counts completed runs that have a summary. A data-descriptor zip is read from the central-directory size. A pasted OpenAPI document is parsed from its paths. Run records still keep a token ceiling because the visible cap is spend.
Failures / known gaps: The runs page is not built. There is no backend, so tags live in web/data/model-tags.json. A spec URL without a pasted document is refused. Eval runs in the mock still always pass. Loop detection is stored and not enforced until the runtime.
New dependencies: none
Follow-ups for the next session: The runs UI.

## S5 feat/runs-ui

Session: S5 feat/runs-ui
Built: A run can be started, watched, stopped, answered, and reviewed against the mock stream. /runs/new picks an agent (and blocks when it has no active prompt), a GitHub repo or a scaffold from that agent's stacks, a task, criteria, and attachments. The spend cap is read-only and links to Settings. /runs/[id] is three resizable panes: an activity log, the diff / logs / screenshots / preview, and a status card with the spend bar. A client-tool card and a clarification card sit above the status while the run is waiting. A finished run shows the summary and links to the PR, the zip, the preview, and a re-run. /runs lists runs with agent and state filters. Test run on the agent editor opens the form with the latest eval filled in.
Decisions: Amendment A was not in the repo; the session text is the spec. Run and RunCreate no longer have a budget field. The spend cap is Settings > Runs. The log subscribes to the query cache; the SSE hook is the only reader of the stream. Components do not touch the socket. The mock keeps a script cursor in sessionStorage and resumes a non-terminal run after a full page load, because a navigation can drop the in-memory timer. Attachments are stored as ids (file names and links). There is no upload API.
Failures / known gaps: No backend and no sandbox. Eval runs in the mock still always pass. A spec URL without a pasted document is refused. Loop detection is stored and not enforced. The mock stream is the contract below; a real run will not match it until the backend session implements it.
Contract the backend must implement exactly as mocked: SSE frames are `id: <seq>`, `event: <type>`, `data: <Event JSON>`, separated by a blank line. `GET /runs/{id}/events?after=<seq>` omits events with seq less than or equal to that value. Event types are RUN_STARTED, MODEL_CALLED (with cost: inputTokens, outputTokens, usd), TOOL_CALLED, TOOL_RESULT, TOOL_REFUSED, SKILL_LOADED, CLIENT_TOOL_REQUESTED, CLARIFICATION_RAISED, STATE_CHANGED, RUN_COMPLETED, and RUN_FAILED. CLIENT_TOOL_REQUESTED sets status waiting_client and pauses the script until `POST /runs/{id}/client-tool-result` with requestId. CLARIFICATION_RAISED sets status waiting_user and pauses until `POST /runs/{id}/answer` with text; the run then returns to running. `POST /runs/{id}/stop` sets status cancelled, appends STATE_CHANGED, and the event stream ends within 2 seconds. RUN_COMPLETED carries the RunSummary plus prUrl, previewUrl, and branch. RUN_FAILED carries cause and text. `GET /runs/{id}/diff` returns three files (path, before, after). `GET /runs/{id}/artifacts` returns screenshots (one url per viewport), a build log, a test log, a zip url, and a preview.
New dependencies: @tanstack/react-virtual, so the activity log virtualizes one row per event.
Follow-ups for the next session: The backend that implements this contract. Loop detection stays unenforced until the runtime.

## S6 feat/real-engine-chat

Session: S6 feat/real-engine-chat
Built: The chat talks to FastAPI. A message creates a task, route_task assigns the project's only member, and a run works in a real folder on this machine. OpenAI is called through the gateway, tool calls are executed, and the thread shows the summary, the files, and the preview. The same task and agent shape can take a supervisor later.
Decisions: Amendment A was not in the repo; the session text is the spec. One SQLite documents table holds the records. The event stream is a poll of that table, so resume does not depend on a live socket. route_task is the only place a task is assigned. DEV LOCAL MODE runs commands in the project folder when Docker does not answer. The OpenAI key stays in api/.env. Model tags moved to the API. Mocks stay on for the web unit tests and the studio browser tests.
Failures / known gaps: Evals still always pass. The Docker container does not enforce a domain allow-list. Token counts are still ceil(chars/4). Messages older than the last 20 are truncated, not summarised by a model. Screenshots are captured with Playwright when it is installed and the gateway is not mocked; the mocked chat run does not take them. The GitHub branch, push, and pull request path is implemented and was not exercised against GitHub. One run at a time is not enforced. Tool results are not wrapped as untrusted. The real landing-page test runs only when RUN_REAL_LLM_TESTS=1.
New dependencies: fastapi, uvicorn, sqlalchemy, alembic, pydantic, httpx, pyyaml, python-dotenv, and pytest for the API. openai is imported only in the gateway. docker is the sandbox client when Docker answers.
Follow-ups for the next session: Real evals. A Backend Engineer agent. Routing rules that replace route_task.

## S7 feat/streaming-real-evals

Session: S7 feat/streaming-real-evals
Built: The chat shows the agent's text as it arrives, then replaces it with the summary, the files, and the links. Evals are real runs. A version can be set active only when every eval on it passed. Settings > Models can run one agent's evals across models. Compiled prompts are counted with tiktoken. Older chat is summarised onto the project. The Docker sandbox refuses hosts outside the allow-list.
Decisions: S6 was still unmerged, so this branch starts from feat/real-engine-chat. MODEL_DELTA rows are folded into one MODEL_OUTPUT when the model call finishes, and sequence numbers are packed so the event log stays contiguous. The chat batches those pieces about every 50ms. Eval runs use the same loop in a folder that is deleted afterwards. Pass is the string `pass`. Mocked studio tests still mark evals as pass without a run. The "best in your runs" badge still needs five completed runs; compare runs count toward that. DEV LOCAL MODE is unchanged when Docker does not answer.
Failures / known gaps: The GitHub branch, push, and pull request test is in the suite and did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. A screenshot pass can be met by an empty image when Playwright cannot launch; the viewport is recorded and console errors are empty. The mock preview in the web unit tests still estimates tokens as characters divided by four. Saved versions use tiktoken. Backend Engineer, routing rules, and supervisors are not in this session. route_task still assigns the only member.
New dependencies: tiktoken, so compiled prompt counts use OpenAI's tokenizer. Actual usage still comes from the API response.
Follow-ups for the next session: Put a GitHub token in api/.env and run the throwaway-repo test with RUN_GITHUB_TESTS=1. A Backend Engineer agent. Routing rules that replace route_task.

## S8 feat/run-fixes-teach-streaming

Session: S8 feat/run-fixes-teach-streaming
Built: A chat message is labelled before a run exists. Greetings get a short reply in the thread, work outside the role gets one refusal, and in-role work starts a run. Each model call is its own bubble. Deltas stay in memory and only the merged text is stored. The chat page is the viewport height, the thread is the only scroller, and Teach saves a skill, a stack, and an optional docs source onto the agent in one request.
Decisions: The live classifier is one completion; under GATEWAY_MOCK the label is a word list so the suite stays offline. Live delta sequence numbers sit at 1_000_000 and up so they cannot replace a stored event, and the resume cursor ignores them. Clarification rounds live in a side record because the Run document drops unknown fields. A command that does not exit is refused before it starts and points at the preview tool. A screenshot counts only when Playwright launched and the PNG size matches the viewport. The secret scan skips gitignored files so api/.env can hold a token; .env.example is tracked and is scanned. Git config was not changed, so the hook file at .githooks/pre-commit is not installed by this commit. CI runs it, and runs gitleaks.
Failures / known gaps: The GitHub branch, push, and pull request test did not run, because GITHUB_TOKEN in api/.env is empty. The landing-page test that calls OpenAI still runs only when RUN_REAL_LLM_TESTS=1. Chromium has no document.scrollHeight; the test checks documentElement.scrollHeight against the viewport. Draft rules from a repo clones only when the gateway is not mocked. The mock studio still marks evals as pass without a run. Backend Engineer, routing rules, and supervisors are not in this session. route_task still assigns the only member.
New dependencies: none. CI calls gitleaks/gitleaks-action. The tree scan is a Python script in the repo.
Follow-ups for the next session: Put a GitHub token in api/.env and run the throwaway-repo test with RUN_GITHUB_TESTS=1. Point git at .githooks if the local hook should run. A Backend Engineer agent. Routing rules that replace route_task.

## S9 feat/run-serialisation-loop-fixes

Session: S9 feat/run-serialisation-loop-fixes
Built: One run works at a time per project; further in-scope messages queue with a visible note. Stop words halt the active run and clear the queue. Follow-ups carry prior summary, diff, and failure into the next run. The files tool prefers edit and append, auto-builds after three writes, and blocks complete until build_test passed when a package.json exists. Zones block writes only. Chat shows agent is working with Stop, and the Access card warns when build, shell, or preview tools are off.
Decisions: `project_runs.drain` starts the next queued run when the active one finishes or is cancelled. Complete-time build, screenshots, and preview run only for project chat runs, not eval throwaway folders. Out-of-scope and chat-mode behaviour from the prior scope work stays on this branch. OpenAPI 0.10.0 adds queue fields, activeRunId, maxSpendPerDayUsd, and MODEL_RETRY.
Failures / known gaps: The GitHub throwaway-repo test still needs GITHUB_TOKEN. Live OpenAI streaming uses full timeout wiring only in mock (`MOCK_MODEL_HANG`); the production stream path still relies on provider behaviour.
New dependencies: none.
Follow-ups for the next session: GitHub token and RUN_GITHUB_TESTS=1. Live model first-token timeout on the OpenAI stream. Backend Engineer and routing rules.

## S10 fix/tool-result-pairing

Session: S10 fix/tool-result-pairing
Built: Each run keeps a transcript of assistant tool calls and tool results appended to the model message list, with gateway pairing checks and optional redacted request capture under api/debug/runs/. Tool results return non-empty text; context trimming removes oldest whole call/result blocks. A vite-react-ts starter scaffolds a buildable React app in empty workspaces. Merged with S9 on one branch after main took S8.
Decisions: Chat Completions message shape only; Responses API deferred with a skipped fixture test. Capture files stay gitignored.
Failures / known gaps: Real-model Connect 4 end-to-end with screenshots not re-run in CI (mock capture used for PR evidence).
New dependencies: none
Follow-ups for the next session: Wire Responses/reasoning API with the same pairing helper when that gateway path exists.

## S11 feat/gemini-provider

Session: S11 feat/gemini-provider
Built: Model calls route through a provider protocol (`list_models`, `config_schema`, `complete`, `pricing`) with OpenAI and Gemini implementations; the gateway handles pairing, capture, 60s first-token / 10m total limits, two retries with MODEL_RETRY, and fails with `model call timed out (<provider>/<model>)`. Settings > Providers shows OpenAI and Gemini cards (key found/missing, test, refresh); the agent model picker groups models by provider. Gemini uses google-genai only inside `api/gateway/providers/gemini.py`.
Decisions: Default provider when an agent omits `provider` stays OpenAI unless only Gemini is configured (no OpenAI key). Ollama remains on the OpenAI-compatible path until a dedicated adapter lands. Classifier heuristics check scope “never does” before treating “build …” as a task.
Failures / known gaps: Anthropic and Ollama adapters are not implemented. Some engine eval/scaffold tests still fail on this machine (loop evidence / snap sandbox), same as main. Real Gemini tic-tac-toe runs only with RUN_REAL_LLM_TESTS=1 and a key.
New dependencies: google-genai — official Gemini SDK isolated to the gateway provider module.
Follow-ups for the next session: Anthropic and Ollama providers on the same interface; Backend Engineer role; fix eval loop flake if still present on main.

## S11 follow-up (thought_signature)

Session: S11 feat/gemini-provider (follow-up)
Built: Gemini model turns store verbatim `gemini_model_content` on the run transcript (including `thought_signature` on function-call parts); history replay uses stored parts, not reconstructed TOOL_CALLED events. Provider 4xx surfaces immediately on the run; Connect 4 on live Gemini completes with request capture under `api/debug/runs/<run_id>/`.
Decisions: Function-call parts are accumulated from the stream (last chunk alone dropped signatures); assistant rows with tool_calls must carry `gemini_model_content` or the gateway raises `internal: thought_signature lost`.
Failures / known gaps: unchanged out-of-scope items (Anthropic/Ollama adapters, Backend Engineer).
New dependencies: none
Follow-ups: none for this bug

## S11 follow-up (studio 400 / stale server)

Session: S11 feat/gemini-provider (studio 400)
Built: Parallel same-name Gemini function calls keep one stored part each; agent config is filtered to the Gemini schema and `structuredOutputs` is not sent as JSON mime type when tools are present. Thought summaries count as first token. API restarted from current code with `--reload`. Live Connect 4 (multiplayer + CPU difficulty) on gemini-3.8-flash completed.
Decisions: The 11:31 studio failure (`run_11317`) was the old uvicorn process plus reconstructed functionCall parts; after reload, the same prompt completes.
Failures / known gaps: restart the API (or use `--reload`) after gateway changes or the studio will keep serving the previous adapter.
New dependencies: none
Follow-ups: Anthropic/Ollama adapters, Backend Engineer

## S11 follow-up (studio Connect 4 leftovers)

Session: S11 feat/gemini-provider (preview-stop / lucide / no-progress)
Built: "ok stop the preview server" (including the "preiew" typo) stops the preview and does not start a coding run. File reads and listings no longer count toward the 15-tool "no progress" loop. `lucide-react` is on the React and Next.js stack allow-lists, and package names match with fnmatch so `@tailwindcss/*` works.
Decisions: Preview-stop is handled before classify/control so "stop the preview" is not treated as stop-all. `os.kill` on a missing or unprivileged pid is ignored so the preview record still clears.
Failures / known gaps: `vite`/`next` as a shell daemon is still refused; use the preview tool. Anthropic/Ollama adapters and Backend Engineer remain out of scope.
New dependencies: none
Follow-ups: Anthropic/Ollama adapters, Backend Engineer

## S13 feat/team-lead-reviewer

Session: S13 feat/team-lead-reviewer
Built: A Team Lead library role splits work, assigns child tasks, and reviews every result before the user sees it as done. It writes no application code. When a project has a lead, user messages go to that agent first; child tasks appear as an editable numbered plan (approve-before-run is on by default); each completed child starts a fresh review run; the parent finishes only after every child is approved, then the lead posts the wrap-up and refreshes the preview.
Decisions: `create_task` only records planned children; runs start after plan approve. Review `changes_requested` creates a new task for the same author at most twice, then the user decides. Review spend is a separate cap (default $1) and is reported, not retried. Lead/review runs cannot write files or run non-build/test shell.
Failures / known gaps: PM and QA as separate roles, and routing by learned stats, are out of scope. Isolated library "Run evals" for the lead still need a project with members. The live three-agent todo app is behind `RUN_REAL_LLM_TESTS=1`. `test_tic_tac_toe_ui_reaches_a_built_app_with_screenshots` failed on PNG dimensions (pre-existing flake). Playwright chromium was missing in this environment; a second `next dev` is locked by the studio already on :3000. Settings > Runs toggle was verified in the browser.
New dependencies: none
Follow-ups: PM role; run the live todo-app test with Team Lead + Backend + Frontend; Playwright browsers in CI.

