import type { components } from "@/lib/api/generated/types"
import { compilePrompt } from "@/features/agents/compile"
import seed from "@/mocks/seed.generated.json"

type Agent = components["schemas"]["AgentDefinition"]
type PromptVersion = components["schemas"]["PromptVersion"]
type Tool = components["schemas"]["ToolDefinition"]
type Skill = components["schemas"]["Skill"]
type Stack = components["schemas"]["TechStack"]
type DataSource = components["schemas"]["DataSource"]
type ModelCard = Omit<components["schemas"]["ModelInfo"], "ownStats">
type Run = components["schemas"]["Run"]
type Event = components["schemas"]["Event"]
type Artifact = components["schemas"]["Artifact"]
type TextDiff = components["schemas"]["TextDiff"]

export type Db = {
  agents: Agent[]
  versions: PromptVersion[]
  tools: Tool[]
  skills: Skill[]
  stacks: Stack[]
  dataSources: DataSource[]
  models: ModelCard[]
  runs: Run[]
  events: Event[]
  diffs: Record<string, TextDiff[]>
  artifacts: Record<string, Artifact[]>
}

const emptySchema = { type: "object", additionalProperties: false }

function tool(
  id: string,
  permission: Tool["permission"],
  description: string,
  properties: Record<string, unknown>,
  required: string[],
): Tool {
  return {
    id,
    kind: "builtin",
    name: id,
    description,
    schema: { ...emptySchema, properties, required },
    permission,
    config: {},
    source: "builtin",
    enabled: true,
  }
}

const tools: Tool[] = [
  tool("shell", "write", "Run a command in the workspace.", { command: { type: "string" } }, ["command"]),
  tool("files", "write", "Read and write files inside the agent zones.", { path: { type: "string" } }, ["path"]),
  tool("package_install", "write", "Install a package that is on an enabled allow-list.", { name: { type: "string" } }, ["name"]),
  tool("build_test", "write", "Run the project build and tests.", {}, []),
  tool("headless_browser", "external", "Open a page and capture a screenshot.", { url: { type: "string" } }, ["url"]),
  tool("preview_deploy", "external", "Publish the workspace preview.", {}, []),
  tool("search_data", "read", "Search the data sources attached to this agent.", { query: { type: "string" } }, ["query"]),
  tool("load_skill", "read", "Load a skill body into the context.", { name: { type: "string" } }, ["name"]),
  tool("complete", "write", "Finish the run with a summary.", { summary: { type: "object" } }, ["summary"]),
  tool("raise_clarification", "read", "Ask the user a question and wait.", { question: { type: "string" } }, ["question"]),
  tool("escalate", "external", "Hand the run to a person.", { reason: { type: "string" } }, ["reason"]),
]

const authored = seed as unknown as {
  agent: Agent
  sections: PromptVersion["sections"]
  skills: Skill[]
  stacks: Stack[]
  dataSources: DataSource[]
  models: ModelCard[]
}

function ordered<T extends { id: string }>(items: T[], ids: string[]): T[] {
  return ids.flatMap((id) => {
    const item = items.find((candidate) => candidate.id === id)
    return item ? [item] : []
  })
}

function initialVersion(): PromptVersion {
  const compiled = compilePrompt({
    sections: authored.sections,
    stacks: ordered(authored.stacks, authored.agent.stackIds).map((stack) => ({
      name: stack.name,
      version: stack.version,
    })),
    tools: ordered(tools, authored.agent.toolIds).map((item) => ({
      name: item.name,
      description: item.description,
    })),
    skills: ordered(authored.skills, authored.agent.skillIds).map((skill) => ({
      name: skill.name,
      description: skill.description,
    })),
  })
  return {
    id: "pv_frontend_engineer_1",
    agentId: authored.agent.id,
    version: 1,
    sections: authored.sections,
    compiled: compiled.compiled,
    tokenCount: compiled.tokenCount,
    smokeEvalStatus: "not_run",
    createdAt: "2026-10-01T00:00:00.000Z",
  }
}

function initialRuns(versionId: string): Pick<Db, "runs" | "events" | "diffs" | "artifacts"> {
  const agentId = authored.agent.id
  const model = { provider: authored.agent.model.provider, name: authored.agent.model.name }
  const budget = authored.agent.budgets
  const runs: Run[] = [
    {
      id: "run_completed",
      agentId,
      promptVersionId: versionId,
      model,
      workspace: { kind: "repo", url: "https://github.com/example/atelier-fixtures" },
      task: "Add a primary button to the empty state.",
      criteria: ["The button is visible", "The build passes"],
      attachmentIds: [],
      budget,
      status: "completed",
      iterations: 4,
      tokensIn: 1200,
      tokensOut: 400,
      costUsd: 0.04,
      summary: {
        description: "Added a primary button on the empty state.",
        filesChanged: ["src/Empty.tsx"],
        dependencies: [],
        criteria: [
          { text: "The button is visible", evidence: "src/Empty.tsx renders Button" },
          { text: "The build passes", evidence: "build_test returned exit 0" },
        ],
        assumptions: [],
        followUps: [],
      },
      branch: "feat/empty-button",
      prUrl: "https://github.com/example/atelier-fixtures/pull/1",
      startedAt: "2026-10-02T12:00:00.000Z",
      endedAt: "2026-10-02T12:05:00.000Z",
    },
    {
      id: "run_failed",
      agentId,
      promptVersionId: versionId,
      model,
      workspace: { kind: "scaffold", template: "vite-react-ts" },
      task: "Replace the header.",
      criteria: ["The header reads Studio"],
      attachmentIds: [],
      budget,
      status: "failed",
      terminalCause: "error",
      iterations: 2,
      tokensIn: 300,
      tokensOut: 80,
      costUsd: 0.01,
      startedAt: "2026-10-03T12:00:00.000Z",
      endedAt: "2026-10-03T12:02:00.000Z",
    },
    {
      id: "run_cancelled",
      agentId,
      promptVersionId: versionId,
      model,
      workspace: { kind: "repo", url: "https://github.com/example/atelier-fixtures" },
      task: "Move the nav to the left.",
      criteria: ["Nav is on the left"],
      attachmentIds: [],
      budget,
      status: "cancelled",
      iterations: 1,
      tokensIn: 100,
      tokensOut: 20,
      costUsd: 0,
      startedAt: "2026-10-04T12:00:00.000Z",
      endedAt: "2026-10-04T12:01:00.000Z",
    },
  ]
  const events: Event[] = [
    event("run_completed", 1, "RUN_STARTED", "2026-10-02T12:00:00.000Z"),
    event("run_completed", 2, "RUN_COMPLETED", "2026-10-02T12:05:00.000Z"),
    event("run_failed", 1, "RUN_STARTED", "2026-10-03T12:00:00.000Z"),
    event("run_failed", 2, "RUN_FAILED", "2026-10-03T12:02:00.000Z", { message: "build failed" }),
    event("run_cancelled", 1, "RUN_STARTED", "2026-10-04T12:00:00.000Z"),
    event("run_cancelled", 2, "STATE_CHANGED", "2026-10-04T12:01:00.000Z", { status: "cancelled" }),
  ]
  return {
    runs,
    events,
    diffs: {
      run_completed: [{ path: "src/Empty.tsx", before: "", after: "export function Empty() { return <button>Start</button> }\n" }],
    },
    artifacts: {
      run_completed: [
        { id: "shot_desktop", name: "desktop.png", kind: "screenshot", viewport: "1280x800", url: "/fixtures/desktop.png" },
      ],
    },
  }
}

function event(
  runId: string,
  seq: number,
  type: Event["type"],
  occurredAt: string,
  payload: Record<string, unknown> = {},
): Event {
  return {
    id: `${runId}_${seq}`,
    runId,
    seq,
    type,
    actor: { kind: "agent", role: "frontend-engineer" },
    payload,
    occurredAt,
  }
}

export function createDb(): Db {
  const version = initialVersion()
  const history = initialRuns(version.id)
  return {
    agents: [structuredClone(authored.agent)],
    versions: [version],
    tools: structuredClone(tools),
    skills: structuredClone(authored.skills),
    stacks: structuredClone(authored.stacks),
    dataSources: structuredClone(authored.dataSources),
    models: structuredClone(authored.models),
    runs: history.runs,
    events: history.events,
    diffs: history.diffs,
    artifacts: history.artifacts,
  }
}

export let db = createDb()
let counter = 100

export function resetDb() {
  db = createDb()
  counter = 100
  for (const timer of liveTimers.values()) clearInterval(timer)
  liveTimers.clear()
}

export function nid(prefix: string) {
  counter += 1
  return `${prefix}_${counter}`
}

export function now() {
  return new Date().toISOString()
}

export function orderedById<T extends { id: string }>(items: T[], ids: string[]) {
  return ordered(items, ids)
}

const liveTimers = new Map<string, ReturnType<typeof setInterval>>()

const script: { type: Event["type"]; payload: Record<string, unknown> }[] = [
  { type: "RUN_STARTED", payload: {} },
  { type: "STATE_CHANGED", payload: { status: "running" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "files" } },
  { type: "TOOL_RESULT", payload: { name: "files", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_REFUSED", payload: { name: "package_install", package: "vue", reason: "not on the allow-list" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "SKILL_LOADED", payload: { name: "react-best-practices" } },
  { type: "TOOL_CALLED", payload: { name: "shell" } },
  { type: "TOOL_RESULT", payload: { name: "shell", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "files" } },
  { type: "TOOL_RESULT", payload: { name: "files", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "build_test" } },
  { type: "TOOL_RESULT", payload: { name: "build_test", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "CLIENT_TOOL_REQUESTED", payload: { requestId: "ctr_1", name: "confirm_copy", input: { text: "Use this heading?" } } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "headless_browser" } },
  { type: "TOOL_RESULT", payload: { name: "headless_browser", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "STATE_CHANGED", payload: { status: "completed" } },
  { type: "RUN_COMPLETED", payload: {} },
]

export function startLiveRun(runId: string) {
  let index = 0
  const timer = setInterval(() => {
    const run = db.runs.find((item) => item.id === runId)
    if (!run || run.status === "cancelled" || run.status === "completed" || run.status === "failed") {
      clearInterval(timer)
      liveTimers.delete(runId)
      return
    }
    if (run.status === "waiting_client" || run.status === "waiting_user") return
    const step = script[index]
    if (!step) {
      clearInterval(timer)
      liveTimers.delete(runId)
      return
    }
    index += 1
    const next = appendEvent(runId, step.type, step.payload)
    if (step.type === "MODEL_CALLED") {
      run.iterations += 1
      run.tokensIn += 100
      run.tokensOut += 40
      run.costUsd = Number((run.costUsd + 0.001).toFixed(4))
      next.cost = { inputTokens: 100, outputTokens: 40, usd: 0.001 }
    }
    if (step.type === "STATE_CHANGED" && step.payload.status === "running") run.status = "running"
    if (step.type === "CLIENT_TOOL_REQUESTED") run.status = "waiting_client"
    if (step.type === "RUN_COMPLETED") {
      run.status = "completed"
      run.endedAt = now()
      run.summary = {
        description: "Mock run finished.",
        filesChanged: [],
        dependencies: [],
        criteria: [],
        assumptions: [],
        followUps: [],
      }
    }
  }, 1200)
  liveTimers.set(runId, timer)
}

export function appendEvent(runId: string, type: Event["type"], payload: Record<string, unknown> = {}): Event {
  const seq = db.events.filter((item) => item.runId === runId).length + 1
  const created: Event = {
    id: nid("evt"),
    runId,
    seq,
    type,
    actor: { kind: type === "STATE_CHANGED" ? "system" : "agent", role: "frontend-engineer" },
    payload,
    occurredAt: now(),
  }
  db.events.push(created)
  return created
}

export function formatSse(item: Event) {
  return `id: ${item.seq}\nevent: ${item.type}\ndata: ${JSON.stringify(item)}\n\n`
}
