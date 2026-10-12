import type { components } from "@/lib/api/generated/types"
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
  budgets: Agent["budgets"]
  toolIds: string[]
  skillIds: string[]
  stackIds: string[]
  zones: string[]
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

const temperature = { type: "number", minimum: 0, maximum: 2, default: 0.2, description: "Sampling temperature" }
const maxOutputTokens = { type: "integer", minimum: 1, maximum: 128000, default: 4096, description: "Maximum tokens to generate" }
const reasoningEffort = { type: "string", enum: ["low", "medium", "high"], default: "medium", description: "How hard the model thinks" }
const webSearch = { type: "boolean", default: false, description: "Allow the model to search the web" }
const structuredOutputs = { type: "boolean", default: false, description: "Require a JSON schema response" }

function objectSchema(properties: Record<string, unknown>) {
  return { type: "object", additionalProperties: false, properties }
}

function modelCard(name: string, speedTier: ModelCard["speedTier"], properties: Record<string, unknown>): ModelCard {
  return {
    provider: "openai",
    name,
    // ponytail: placeholder window until a real provider response replaces this catalog
    contextWindow: 128000,
    priceInPerM: null,
    priceOutPerM: null,
    speedTier,
    fitLine: null,
    configSchema: objectSchema(properties),
    benchmarks: [],
  }
}

export const modelCatalog: ModelCard[] = [
  modelCard("gpt-5", "balanced", { temperature, maxOutputTokens, reasoningEffort, webSearch, structuredOutputs }),
  modelCard("gpt-5-mini", "fast", { temperature, maxOutputTokens, reasoningEffort, structuredOutputs }),
  modelCard("gpt-5-nano", "fast", { temperature, maxOutputTokens }),
  modelCard("o3", "slow", { maxOutputTokens, reasoningEffort, structuredOutputs }),
  modelCard("gpt-4.1", "balanced", { temperature, maxOutputTokens, webSearch }),
  modelCard("gpt-4.1-mini", "fast", { temperature, maxOutputTokens, structuredOutputs }),
]

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
  providers: [{ id: "openai", name: "OpenAI", keyRef: null, connected: false, modelsCachedAt: null }],
  runs: [],
  events: [],
  diffs: {},
  artifacts: {},
})

const STORAGE_KEY = "atelier-mock-db"

function storedDb(): Db | null {
  if (typeof window === "undefined") return null
  const raw = window.sessionStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const saved = JSON.parse(raw) as Db
    return { ...emptyDb(), ...saved, tools: structuredClone(tools) }
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

export let db = createDb()
let counter = 100
let providerSecret: string | null = null

export function resetDb() {
  rememberQueued = false
  if (typeof window !== "undefined") window.sessionStorage.removeItem(STORAGE_KEY)
  db = createDb()
  counter = 100
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
  return freshModels().map((model) => {
    const roleKeys = [...new Set(db.agents.map((agent) => agent.roleKey))]
    const ownStats = roleKeys.flatMap((roleKey) => {
      const agentIds = new Set(db.agents.filter((agent) => agent.roleKey === roleKey).map((agent) => agent.id))
      const runs = db.runs.filter((run) => run.model.name === model.name && agentIds.has(run.agentId))
      if (runs.length === 0) return []
      const passed = runs.filter((run) => run.status === "completed" && run.summary)
      const avgCostUsd = passed.reduce((sum, run) => sum + run.costUsd, 0) / (passed.length || 1)
      return [{ roleKey, runs: runs.length, passed: passed.length, avgCostUsd }]
    })
    return { ...model, ownStats }
  })
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
