import type { components } from "@/lib/api/generated/types"
import { ownStatsFor } from "@/lib/models/stats"
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
  providers: components["schemas"]["ProviderStatus"][]
  runs: Run[]
  runSettings: components["schemas"]["RunSettings"]
  events: Event[]
  diffs: Record<string, TextDiff[]>
  artifacts: Record<string, Artifact[]>
  liveCursors: Record<string, number>
  modelTags: Record<string, { tags: string[]; note: string; heuristic: boolean }>
}

const emptySchema = { type: "object", additionalProperties: false }

function tool(
  id: string,
  permission: Tool["permission"],
  description: string,
  properties: Record<string, unknown>,
  required: string[],
  kind: Tool["kind"] = "builtin",
): Tool {
  return {
    id,
    kind,
    name: id,
    description,
    schema: { ...emptySchema, properties, required },
    permission,
    config: {},
    source: kind === "control" ? "control" : "builtin",
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
  tool("load_skill", "read", "Load a skill body into the context.", { name: { type: "string" } }, ["name"], "control"),
  tool("complete", "write", "Finish the run with a summary.", { summary: { type: "object" } }, ["summary"], "control"),
  tool("raise_clarification", "read", "Ask the user a question and wait.", { question: { type: "string" } }, ["question"], "control"),
  tool("escalate", "external", "Hand the run to a person.", { reason: { type: "string" } }, ["reason"], "control"),
]

type LibraryAgent = {
  id: string
  name: string
  roleKey: string
  description: string
  model: Agent["model"]
  toolIds: string[]
  skillIds: string[]
  stackIds: string[]
  zones: string[]
  scope?: { does: string[]; neverDoes: string[]; zones: string[] }
  sections: PromptVersion["sections"]
  evals: Agent["evals"]
}

export type Library = {
  agents: LibraryAgent[]
  skills: Skill[]
  stacks: Stack[]
  dataSources: DataSource[]
}

export const library = (seed as { library: Library }).library

export const MODEL_CACHE_MS = 60 * 60 * 1000

function ordered<T extends { id: string }>(items: T[], ids: string[]): T[] {
  return ids.flatMap((id) => {
    const item = items.find((candidate) => candidate.id === id)
    return item ? [item] : []
  })
}

const emptyDb = (): Db => ({
  agents: [],
  versions: [],
  tools: structuredClone(tools),
  skills: [],
  stacks: [],
  dataSources: [],
  models: [],
  providers: [
    { id: "openai", name: "OpenAI", keyRef: null, connected: false, modelsCachedAt: null },
    { id: "gemini", name: "Google Gemini", keyRef: null, connected: false, modelsCachedAt: null },
  ],
  runs: [],
  runSettings: {
    maxSpendPerRunUsd: 5,
    maxSpendPerDayUsd: 20,
    maxIterations: 60,
    maxMinutes: 45,
    loopDetection: true,
    recordModelRequests: false,
    approvePlansBeforeRunning: true,
    maxSpendPerReviewUsd: 1,
  },
  events: [],
  diffs: {},
  artifacts: {},
  liveCursors: {},
  modelTags: {},
})

const STORAGE_KEY = "atelier-mock-db"

function storedDb(): Db | null {
  if (typeof window === "undefined") return null
  const raw = window.sessionStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const saved = JSON.parse(raw) as Db
    const builtinIds = new Set(tools.map((item) => item.id))
    const extra = (saved.tools ?? []).filter((item) => !builtinIds.has(item.id) && item.kind !== "control")
    const base = emptyDb()
    return {
      ...base,
      ...saved,
      tools: [...structuredClone(tools), ...extra],
      runSettings: saved.runSettings ?? base.runSettings,
      modelTags: saved.modelTags ?? {},
    }
  } catch {
    return null
  }
}

export function createDb(): Db {
  return storedDb() ?? emptyDb()
}

let rememberQueued = false

export function remember() {
  if (typeof window === "undefined" || rememberQueued) return
  rememberQueued = true
  queueMicrotask(() => {
    rememberQueued = false
    if (typeof window === "undefined") return
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(db))
  })
}

function highestId(value: unknown) {
  let max = 100
  const visit = (node: unknown) => {
    if (typeof node === "string") {
      const match = /_(\d+)$/.exec(node)
      if (match) max = Math.max(max, Number(match[1]))
      return
    }
    if (Array.isArray(node)) {
      for (const item of node) visit(item)
      return
    }
    if (node && typeof node === "object") {
      for (const item of Object.values(node)) visit(item)
    }
  }
  visit(value)
  return max
}

export let db = createDb()
let counter = highestId(db)
let providerSecret: string | null = null

export function resetDb() {
  rememberQueued = false
  if (typeof window !== "undefined") window.sessionStorage.removeItem(STORAGE_KEY)
  db = createDb()
  counter = highestId(db)
  providerSecret = null
  for (const timer of liveTimers.values()) clearInterval(timer)
  liveTimers.clear()
}

export function setProviderSecret(value: string | null) {
  providerSecret = value
}

export function hasProviderSecret() {
  return Boolean(providerSecret)
}

export function freshModels() {
  const provider = db.providers.find((item) => item.id === "openai")
  if (!provider?.modelsCachedAt) return []
  if (Date.now() - Date.parse(provider.modelsCachedAt) > MODEL_CACHE_MS) return []
  return db.models
}

export function modelList() {
  return freshModels().map((model) => ({
    ...model,
    ownStats: ownStatsFor(model.name, db.agents, db.runs),
  }))
}

export function nid(prefix: string) {
  counter += 1
  remember()
  return `${prefix}_${counter}`
}

export function now() {
  remember()
  return new Date().toISOString()
}

export function orderedById<T extends { id: string }>(items: T[], ids: string[]) {
  return ordered(items, ids)
}

const liveTimers = new Map<string, ReturnType<typeof setInterval>>()

function svgShot(label: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="100%" height="100%" fill="#e8e8e8"/><text x="16" y="96" font-size="20">${label}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

const desktopShot = svgShot("desktop")
const mobileShot = svgShot("mobile")
const runSummary = {
  description: "Added a primary button to the page.",
  filesChanged: ["src/App.tsx", "src/button.tsx", "package.json"],
  dependencies: [] as string[],
  criteria: [{ text: "The button is visible", evidence: "https://example.com/preview" }],
  assumptions: ["The page is a client component."],
  followUps: ["Add a hover state."],
}

const script: { type: Event["type"]; payload: Record<string, unknown> }[] = [
  { type: "RUN_STARTED", payload: {} },
  { type: "STATE_CHANGED", payload: { status: "running" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "shell", command: "ls" } },
  { type: "TOOL_RESULT", payload: { name: "shell", ok: true, output: "src" } },
  { type: "CLIENT_TOOL_REQUESTED", payload: { requestId: "ctr_1", name: "confirm_copy", prompt: "Use this heading?" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "CLARIFICATION_RAISED", payload: { question: "Which button label should the page use?" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "files", path: "src/App.tsx" } },
  { type: "TOOL_RESULT", payload: { name: "files", ok: true } },
  { type: "SKILL_LOADED", payload: { name: "react-best-practices" } },
  { type: "TOOL_REFUSED", payload: { name: "package_install", package: "vue", reason: "not on the allow-list" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "build_test" } },
  { type: "TOOL_RESULT", payload: { name: "build_test", ok: true, log: "\u001b[32mbuild ok\u001b[0m\n\u001b[32mtests ok\u001b[0m" } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "headless_browser", viewport: "1280x800" } },
  { type: "TOOL_RESULT", payload: { name: "headless_browser", viewport: "1280x800", screenshotUrl: desktopShot } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "headless_browser", viewport: "390x844" } },
  { type: "TOOL_RESULT", payload: { name: "headless_browser", viewport: "390x844", screenshotUrl: mobileShot } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "shell", command: "git status" } },
  { type: "TOOL_RESULT", payload: { name: "shell", ok: true } },
  { type: "MODEL_CALLED", payload: {} },
  { type: "TOOL_CALLED", payload: { name: "files", path: "src/button.tsx" } },
  { type: "TOOL_RESULT", payload: { name: "files", ok: true } },
  { type: "STATE_CHANGED", payload: { status: "completed" } },
  {
    type: "RUN_COMPLETED",
    payload: {
      summary: runSummary,
      prUrl: "https://github.com/example/repo/pull/1",
      previewUrl: "https://example.com/preview",
      branch: "feat/mock-run",
    },
  },
]

export function startLiveRun(runId: string) {
  if (liveTimers.has(runId)) return
  let index = db.liveCursors[runId] ?? 0
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
    db.liveCursors[runId] = index
    const next = appendEvent(runId, step.type, step.payload)
    if (step.type === "MODEL_CALLED") {
      run.iterations += 1
      run.tokensIn += 100
      run.tokensOut += 40
      run.costUsd = Number((run.costUsd + 0.12).toFixed(2))
      next.cost = { inputTokens: 100, outputTokens: 40, usd: 0.12 }
    }
    if (step.type === "STATE_CHANGED" && step.payload.status === "running") run.status = "running"
    if (step.type === "CLIENT_TOOL_REQUESTED") run.status = "waiting_client"
    if (step.type === "CLARIFICATION_RAISED") run.status = "waiting_user"
    if (step.type === "TOOL_RESULT" && step.payload.name === "build_test") {
      const log = String(step.payload.log ?? "")
      db.artifacts[runId]?.push(
        { id: nid("art"), name: "build.log", kind: "log", url: `data:text/plain,${encodeURIComponent(log)}` },
        { id: nid("art"), name: "test.log", kind: "log", url: `data:text/plain,${encodeURIComponent("tests passed")}` },
      )
    }
    if (step.type === "TOOL_RESULT" && step.payload.name === "headless_browser") {
      const viewport = String(step.payload.viewport ?? "screen")
      db.artifacts[runId]?.push({
        id: nid("art"),
        name: `${viewport}.svg`,
        kind: "screenshot",
        viewport,
        url: String(step.payload.screenshotUrl ?? ""),
      })
    }
    if (step.type === "RUN_COMPLETED") {
      run.status = "completed"
      run.endedAt = now()
      run.summary = runSummary
      run.prUrl = "https://github.com/example/repo/pull/1"
      run.previewUrl = "https://example.com/preview"
      run.branch = "feat/mock-run"
      db.artifacts[runId]?.push(
        { id: nid("art"), name: "workspace.zip", kind: "zip", url: "https://example.com/workspace.zip" },
        { id: nid("art"), name: "preview", kind: "preview", url: "https://example.com/preview" },
      )
    }
  }, 1300)
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

const terminalRun = new Set(["completed", "failed", "cancelled"])

if (typeof window !== "undefined") {
  for (const run of db.runs) {
    if (!terminalRun.has(run.status)) startLiveRun(run.id)
  }
}
